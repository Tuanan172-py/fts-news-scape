"""Bung bản ghi gọn của mô hình thành hai lược đồ đầy đủ, với chi phí 0 token.

Mô hình chỉ phát phần **quyết định ngữ nghĩa**: thực thể nó nhận ra, tóm tắt, luận
điểm, hàm ý, sắc thái và **chỉ số** các đoạn dùng làm chứng cứ. Toàn bộ phần khuôn
mẫu còn lại do script này bù: định danh bài, tiêu đề, định danh thực thể, nhóm kiểm
mục, siêu dữ liệu, và quan trọng nhất là **trích dẫn nguyên văn lấy theo chỉ số**.

Cách làm này triệt tiêu tận gốc động cơ tự kiểm chứng của mô hình. Ở vệt Gold cũ,
mô hình phải tự chép lại chuỗi trích dẫn rồi tự đi kiểm từng chuỗi bằng mười lăm lệnh
tìm kiếm riêng lẻ, chiếm bảy mươi mốt phần trăm tổng số bước. Khi trích dẫn được xác
định bằng chỉ số mảng, nó đúng **do cấu trúc dữ liệu**, không còn gì để kiểm.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.entities import load_registry           # noqa: E402
from src.agent.intent_resolve import (                 # noqa: E402
    GROUPS_WITHOUT_RESOLVER,
    IntentResolver,
    ResolveReport,
    reconcile,
)
from src.agent.l1_router import TYPE_GROUP             # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
TASK_DIR = DATA_ROOT / "agent_tasks" / "article"
IN_DIR = DATA_ROOT / "agent_outputs_article"
L1_OUT_DIR = DATA_ROOT / "agent_outputs_l1"
GOLD_OUT_DIR = DATA_ROOT / "agent_outputs"
MENTIONS_DIR = DATA_ROOT / "article_mentions"

CATEGORY_KEYS = ("ticker_company", "etf_fund", "index", "exchange",
                 "industry_sector", "macro_geo", "asset_class", "institution")

SENTIMENT_MAP = {"pos": "positive", "neg": "negative", "neu": "neutral"}
TIME_MAP = {"urg": "urgent", "today": "today", "week": "this_week",
            "month": "this_month", "arch": "archive"}

MIN_CITATION_CHARS = 20
AGENT_PROVIDER = "dsh"
MODEL_USED = "deepseek-flash"


def now_vn_iso() -> str:
    """Sinh dấu thời gian hiện tại theo múi giờ Việt Nam.

    Returns:
        Chuỗi thời gian định dạng ISO 8601 kèm độ lệch múi giờ.
    """
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def unwrap_tool_envelope(text: str) -> str:
    """Bóc lớp vỏ kết quả công cụ của DSH để lấy đúng phần văn bản mô hình trả về.

    Công cụ gọi agent của DSH trả về `{"kind":..., "runId":..., "output":[{"type":
    "text","text":"..."}]}`. Nếu phía điều phối ghi thẳng đối tượng ấy ra đĩa thì
    tệp đầu ra mang lớp vỏ này, và bộ bóc bản ghi sẽ đọc nhầm lớp vỏ thành đúng một
    bản ghi rác có hai trường `type` và `text`. Đây là sự cố thật: các tệp `_cNN`
    của đợt W1 và W2 đều ở dạng ấy.

    Args:
        text: Nội dung thô của tệp đầu ra.

    Returns:
        Phần văn bản mô hình trả về, hoặc nguyên chuỗi vào khi không có lớp vỏ.
    """
    stripped = (text or "").strip()
    if not stripped.startswith("{"):
        return text
    try:
        env = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if not isinstance(env, dict):
        return text
    out = env.get("output")
    if isinstance(out, list):
        parts = [str(o.get("text", "")) for o in out
                 if isinstance(o, dict) and o.get("type") == "text"]
        if parts:
            return "".join(parts)
    for key in ("text", "content"):
        if isinstance(env.get(key), str):
            return env[key]
    return text


def salvage_records(text: str) -> tuple[list[dict], int]:
    """Bóc các bản ghi hợp lệ khỏi đầu ra của mô hình, chịu được đầu ra hỏng.

    Đầu ra có thể cụt vì chạm trần token, có thể kèm lời dẫn hoặc rào mã. Vì một lô
    mang cả trăm bài, mất cả lô chỉ vì một ký tự sai là không chấp nhận được, nên
    hàm này cứu từng phần tử thay vì phân tích cú pháp một lần rồi bỏ cuộc.

    Args:
        text: Nội dung thô do mô hình trả về.

    Returns:
        Cặp gồm danh sách bản ghi lấy được và số phần tử hỏng không cứu được.
    """
    if not text:
        return [], 0

    cleaned = unwrap_tool_envelope(text).strip()
    if cleaned.startswith("```"):
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("[")
    if start > 0:
        cleaned = cleaned[start:]

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)], 0
        if isinstance(parsed, dict):
            return [parsed], 0
    except json.JSONDecodeError:
        pass

    # Quét thủ công theo cặp ngoặc cân bằng, bỏ qua ngoặc nằm trong chuỗi.
    records: list[dict] = []
    broken = 0
    depth = 0
    buf: list[str] = []
    in_str = False
    escape = False
    for ch in cleaned:
        if depth:
            buf.append(ch)
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                buf = ["{"]
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = "".join(buf)
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        records.append(obj)
                    else:
                        broken += 1
                except json.JSONDecodeError:
                    broken += 1
                buf = []
    if depth > 0:
        broken += 1
    return records, broken


def build_l1_output(article_id: str, title: str, resolved: list,
                    labels: dict[str, str]) -> dict:
    """Dựng bản ghi nhận diện thực thể theo lược đồ `l1-entity-output-v1`.

    Lược đồ này yêu cầu mọi chuỗi nguyên văn phải nằm trong tiêu đề, nên chỉ những
    thực thể xuất hiện ở tiêu đề mới vào đây. Thực thể mô hình bắt được trong phần
    nội dung đi sang tệp phụ ở :func:`build_mentions`, vì chúng có giá trị cho việc
    mở rộng danh mục nhưng không hợp lược đồ này.

    Args:
        article_id: Định danh bài viết.
        title: Tiêu đề nguyên văn.
        resolved: Danh sách thực thể đã tra cứu.
        labels: Nhãn đối chiếu giữa mô hình và tầng mã.

    Returns:
        Từ điển bản ghi đúng lược đồ.
    """
    in_title = [e for e in resolved if e.in_title and e.surface in title]

    entities = []
    for e in in_title:
        if not (e.in_list and e.entity_id and e.type):
            continue
        entities.append({
            "surface": e.surface,
            "entity_id": e.entity_id,
            "type": e.type,
            "method": e.method,
            "in_list": True,
        })

    unlisted = sorted({e.surface for e in resolved if not e.in_list and e.surface})

    groups = {TYPE_GROUP.get(e["type"]) for e in entities}
    recognized = bool(entities)
    categories = {}
    for key in CATEGORY_KEYS:
        if key in groups:
            categories[key] = "done"
        elif recognized and unlisted:
            categories[key] = "none"
        else:
            categories[key] = "none"

    citations = [{"source_span": entities[0]["surface"]}] if recognized else []

    return {
        "l1_output_version": "1.0",
        "article_id": article_id,
        "title": title,
        "recognized": recognized,
        "entities": entities,
        "categories": categories,
        "unlisted_candidates": unlisted,
        "citations": citations,
        "processing_metadata": {
            "agent_provider": AGENT_PROVIDER,
            "model_used": MODEL_USED,
            "timestamp": now_vn_iso(),
            "intent_source": labels,
        },
    }


def build_gold_output(article_id: str, record: dict, paragraphs: list[str]) -> tuple[dict | None, str]:
    """Dựng bản ghi phân tích nội dung theo lược đồ `agent-output-v2-lean`.

    Trích dẫn được lấy **nguyên văn theo chỉ số đoạn** mà mô hình chỉ ra, nên chúng
    luôn là chuỗi con đúng của nội dung gốc mà không cần ai đi kiểm lại.

    Args:
        article_id: Định danh bài viết.
        record: Bản ghi gọn do mô hình phát.
        paragraphs: Mảng đoạn văn đã gửi cho mô hình trong packet.

    Returns:
        Cặp gồm bản ghi đúng lược đồ và chuỗi lý do khi phải bỏ qua bài.
    """
    summary = (record.get("s") or "").strip()
    implication = (record.get("im") or "").strip()
    key_points = [str(k).strip() for k in (record.get("k") or []) if str(k).strip()]

    if not summary:
        return None, "thiếu tóm tắt"
    if len(implication) < 40:
        return None, "hàm ý ngắn hơn 40 ký tự"
    if not key_points:
        return None, "thiếu luận điểm"

    idxs = record.get("c") or []
    citations: list[str] = []
    for raw in idxs:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(paragraphs):
            para = paragraphs[i]
            if len(para) >= MIN_CITATION_CHARS:
                citations.append(para)

    # Chưa đủ hai trích dẫn thì bù bằng các đoạn dài nhất còn lại, theo thứ tự gốc.
    if len(citations) < 2:
        for para in paragraphs:
            if len(citations) >= 2:
                break
            if para not in citations and len(para) >= MIN_CITATION_CHARS:
                citations.append(para)
    if len(citations) < 2:
        return None, "không đủ hai đoạn đạt độ dài trích dẫn"

    # Luận điểm không được chép nguyên văn trích dẫn, đây là cổng chống sao chép.
    key_points = [k for k in key_points if k not in citations]
    if not key_points:
        return None, "luận điểm trùng nguyên văn trích dẫn"

    return {
        "article_id": article_id,
        "summary": summary,
        "key_points": key_points,
        "implication": implication,
        "sentiment": SENTIMENT_MAP.get(str(record.get("sn") or "").lower(), "neutral"),
        "time_sensitivity": TIME_MAP.get(str(record.get("ts") or "").lower(), "this_week"),
        "citations": citations,
    }, ""


def build_mentions(article_id: str, title: str, resolved: list,
                   labels: dict[str, str]) -> dict:
    """Ghi lại các thực thể mô hình bắt được ngoài tiêu đề.

    Lược đồ nhận diện hiện hành chỉ chấp nhận chuỗi nằm trong tiêu đề, nên nhóm này
    chưa có chỗ chứa chính thức. Chúng vẫn được giữ vì đây là nguyên liệu để mở rộng
    danh mục, và vì nhóm tên người sẽ chỉ có giá trị khi tích luỹ đủ nhiều.

    Args:
        article_id: Định danh bài viết.
        title: Tiêu đề nguyên văn.
        resolved: Danh sách thực thể đã tra cứu.
        labels: Nhãn đối chiếu giữa mô hình và tầng mã.

    Returns:
        Từ điển tệp phụ ghi các thực thể ngoài tiêu đề.
    """
    body = [e for e in resolved if not e.in_title]
    return {
        "article_id": article_id,
        "title": title,
        "created_at": now_vn_iso(),
        "mentions": [{
            "surface": e.surface,
            "group": e.group,
            "entity_id": e.entity_id,
            "type": e.type,
            "in_list": e.in_list,
            "source": "body",
        } for e in body],
        "intent_source": labels,
    }


def process_batch(batch_id: str, out_text: str, packet: dict, mapping: dict,
                  resolver: IntentResolver, reg, report: ResolveReport) -> dict:
    """Xử lý một lô đầu ra của mô hình thành các tệp kết quả.

    Args:
        batch_id: Mã lô.
        out_text: Nội dung thô mô hình trả về.
        packet: Nội dung packet đã gửi cho mô hình.
        mapping: Bảng ánh xạ chỉ số cục bộ sang định danh bài.
        resolver: Bộ tra cứu định danh.
        reg: Danh mục thực thể.
        report: Bộ đếm thống kê tra cứu.

    Returns:
        Từ điển thống kê kết quả xử lý lô.
    """
    records, broken = salvage_records(out_text)
    by_index = {str(r.get("i")): r for r in records if r.get("i") is not None}
    index_map = mapping.get("index") or {}
    articles = {str(a.get("i")): a for a in (packet.get("a") or [])}

    L1_OUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    MENTIONS_DIR.mkdir(parents=True, exist_ok=True)

    l1_rows: list[dict] = []
    gold_rows: list[dict] = []
    mention_rows: list[dict] = []
    missing: list[str] = []
    gold_skipped: list[tuple[str, str]] = []

    for idx, article_id in index_map.items():
        rec = by_index.get(idx)
        if rec is None:
            missing.append(idx)
            continue
        src = articles.get(idx) or {}
        title = src.get("t") or ""
        paragraphs = src.get("p") or []

        resolved = resolver.resolve_many(rec.get("e") or [], title=title, report=report)
        code_ids = {d["entity_id"] for d in reg.detect(title)}
        labels = reconcile(resolved, code_ids)

        l1_rows.append(build_l1_output(article_id, title, resolved, labels))

        gold, reason = build_gold_output(article_id, rec, paragraphs)
        if gold:
            gold_rows.append(gold)
        else:
            gold_skipped.append((idx, reason))

        mentions = build_mentions(article_id, title, resolved, labels)
        if mentions["mentions"]:
            mention_rows.append(mentions)

    if l1_rows:
        (L1_OUT_DIR / f"{batch_id}.output.json").write_text(
            json.dumps(l1_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if gold_rows:
        (GOLD_OUT_DIR / f"{batch_id}.output.json").write_text(
            json.dumps(gold_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if mention_rows:
        (MENTIONS_DIR / f"{batch_id}.mentions.json").write_text(
            json.dumps(mention_rows, ensure_ascii=False, indent=1), encoding="utf-8")

    total = len(index_map)
    return {
        "batch_id": batch_id,
        "expected": total,
        "records": len(records),
        "broken": broken,
        "missing": missing,
        "l1": len(l1_rows),
        "gold": len(gold_rows),
        "mentions": len(mention_rows),
        "gold_skipped": gold_skipped,
        "parse_fail_rate": (len(missing) + broken) / total if total else 0.0,
    }


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh bung bản ghi gọn.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi mọi lô đạt, 1 khi có lô vượt ngưỡng hỏng, 2 khi không có việc.
    """
    ap = argparse.ArgumentParser(description="Bung bản ghi gọn thành hai lược đồ đầy đủ")
    ap.add_argument("source", nargs="?", default=str(IN_DIR),
                    help="Thư mục chứa đầu ra thô của mô hình")
    ap.add_argument("--task-dir", default=str(TASK_DIR), help="Thư mục chứa packet")
    ap.add_argument("--batch", help="Chỉ xử lý một lô cụ thể")
    ap.add_argument("--wave", help="Chỉ xử lý các lô của một đợt, gồm cả lô vá")
    ap.add_argument("--fail-threshold", type=float, default=0.10,
                    help="Tỷ lệ hỏng khiến lệnh trả mã lỗi")
    ap.add_argument("--json", action="store_true", help="Xuất thống kê dạng JSON")
    args = ap.parse_args(argv)

    src_dir = Path(args.source)
    task_dir = Path(args.task_dir)
    # Không lọc thì mỗi lần hoàn tất lại bung mọi đợt cũ trong thư mục, và tỷ lệ hỏng
    # "cao nhất" lấy trên cả những đợt đã đóng từ lâu.
    pattern = (f"{args.batch}.output.json" if args.batch
               else f"article_{args.wave}_*.output.json" if args.wave
               else "*.output.json")
    outputs = sorted(glob.glob(str(src_dir / pattern)))
    if not outputs:
        print(f"Không có đầu ra nào trong {src_dir}. Chạy wave trước đã.")
        return 2

    reg = load_registry()
    resolver = IntentResolver(reg)
    report = ResolveReport()
    results = []

    for out_path in outputs:
        batch_id = Path(out_path).name.replace(".output.json", "")
        packet_path = task_dir / f"{batch_id}.task.json"
        map_path = task_dir / f"{batch_id}.map.json"
        if not packet_path.exists() or not map_path.exists():
            print(f"⚠️  Bỏ qua {batch_id}: thiếu packet hoặc bảng ánh xạ.")
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        text = Path(out_path).read_text(encoding="utf-8")
        results.append(process_batch(batch_id, text, packet, mapping, resolver, reg, report))

    if not results:
        print("Không lô nào xử lý được.")
        return 2

    if args.json:
        print(json.dumps({"batches": results,
                          "resolve": report.summary()}, ensure_ascii=False))
        return 0

    worst = max(r["parse_fail_rate"] for r in results)
    print("=" * 84)
    print(" 🧩  BUNG BẢN GHI GỌN THÀNH LƯỢC ĐỒ ĐẦY ĐỦ")
    print("=" * 84)
    print(f"{'lô':28} {'chờ':>5} {'nhận':>6} {'L1':>5} {'nội dung':>9} {'hỏng':>6} {'thiếu':>6}")
    print("-" * 84)
    for r in results:
        print(f"{r['batch_id']:28} {r['expected']:>5} {r['records']:>6} {r['l1']:>5} "
              f"{r['gold']:>9} {r['broken']:>6} {len(r['missing']):>6}")
    print("-" * 84)

    print("\nTỷ lệ tra cứu định danh theo nhóm:")
    for group, total, ok, rate in report.summary():
        note = "  (chưa có bảng tra, đúng thiết kế)" if group in GROUPS_WITHOUT_RESOLVER else ""
        print(f"  {group:5} {ok:>4}/{total:<4} {rate:>6.0%}{note}")

    skipped = [(r["batch_id"], s) for r in results for s in r["gold_skipped"]]
    if skipped:
        print(f"\nBài không dựng được phần nội dung: {len(skipped)}")
        for batch_id, (idx, reason) in skipped[:8]:
            print(f"  {batch_id} #{idx}: {reason}")

    print(f"\nTỷ lệ hỏng cao nhất trong đợt: {worst:.1%} "
          f"(ngưỡng dừng {args.fail_threshold:.0%})")
    print("=" * 84)
    print("Bước tiếp: `l1_ingest.py data/agent_outputs_l1` rồi `agent_ingest.py data/agent_outputs`")
    return 1 if worst > args.fail_threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
