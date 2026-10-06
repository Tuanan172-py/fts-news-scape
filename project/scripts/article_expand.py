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
from src.core import paths                             # noqa: E402
from src.agent.intent_resolve import (                 # noqa: E402
    GROUPS_WITHOUT_RESOLVER,
    IntentResolver,
    ResolveReport,
    reconcile,
)
from src.agent.article_contract import (               # noqa: E402,F401
    MIN_CITATION_CHARS,
    SENTIMENT_MAP,
    TIME_MAP,
    parse_and_validate,
    salvage_records,
    unwrap_tool_envelope,
)
from src.agent.l1_router import TYPE_GROUP             # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = paths.article_packets_dir()
IN_DIR = paths.agent_outputs_dir("_article")
L1_OUT_DIR = paths.agent_outputs_dir("_l1")
GOLD_OUT_DIR = paths.agent_outputs_dir()
MENTIONS_DIR = paths.article_mentions_dir()

CATEGORY_KEYS = ("ticker_company", "etf_fund", "index", "exchange",
                 "industry_sector", "macro_geo", "asset_class", "institution")

UNKNOWN_PROVENANCE = "unknown"


def now_vn_iso() -> str:
    """Sinh dấu thời gian hiện tại theo múi giờ Việt Nam.

    Returns:
        Chuỗi thời gian định dạng ISO 8601 kèm độ lệch múi giờ.
    """
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def build_l1_output(article_id: str, title: str, resolved: list,
                    labels: dict[str, str], *,
                    agent_provider: str = UNKNOWN_PROVENANCE,
                    model_used: str = UNKNOWN_PROVENANCE) -> dict:
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
        agent_provider: Nhà cung cấp runtime phân tích.
        model_used: Tên mô hình đã sử dụng.

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
            "agent_provider": agent_provider,
            "model_used": model_used,
            "timestamp": now_vn_iso(),
            "intent_source": labels,
        },
    }


def _is_index(value) -> bool:
    """Kiểm giá trị là chỉ số nguyên thật, loại trừ kiểu logic.

    Args:
        value: Giá trị cần kiểm.

    Returns:
        True khi là `int` và không phải `bool`.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def build_gold_output(article_id: str, record: dict, paragraphs: list[str]) -> tuple[dict | None, str]:
    """Dựng bản ghi phân tích nội dung theo lược đồ `agent-output-v2-lean`.

    Trích dẫn được lấy **nguyên văn theo chỉ số đoạn** mà mô hình chỉ ra, nên chúng
    luôn là chuỗi con đúng của nội dung gốc mà không cần ai đi kiểm lại. Bài chỉ có
    một đoạn văn đạt độ dài trích dẫn thì một trích dẫn là đủ và bản ghi mang dấu
    `citation_basis` để cổng DoD nới ngưỡng tương ứng.

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
    if record.get("sn") not in SENTIMENT_MAP:
        return None, "sn ngoài enum"
    if record.get("ts") not in TIME_MAP:
        return None, "ts ngoài enum"

    eligible = [p for p in paragraphs if len(p) >= MIN_CITATION_CHARS]
    need = 1 if len(eligible) < 2 else 2
    citations: list[str] = []
    for raw in record.get("c") or []:
        if _is_index(raw) and 0 <= raw < len(paragraphs):
            para = paragraphs[raw]
            if len(para) >= MIN_CITATION_CHARS and para not in citations:
                citations.append(para)
    if len(citations) < need:
        return None, "không đủ hai đoạn trích dẫn hợp lệ" if need == 2 else "không đủ trích dẫn hợp lệ"

    # Luận điểm không được chép nguyên văn trích dẫn, đây là cổng chống sao chép.
    key_points = [k for k in key_points if k not in citations]
    if not key_points:
        return None, "luận điểm trùng nguyên văn trích dẫn"

    row = {
        "article_id": article_id,
        "summary": summary,
        "key_points": key_points,
        "implication": implication,
        "sentiment": SENTIMENT_MAP[record["sn"]],
        "time_sensitivity": TIME_MAP[record["ts"]],
        "citations": citations,
    }
    if need == 1:
        row["citation_basis"] = "single-paragraph"
    return row, ""


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


def load_repair_ids(task_dir: Path, batch_id: str) -> set[str]:
    """Gom định danh bài mà các lô vá cùng đợt đã cung cấp.

    Một lô bị cắt cụt thì phần thiếu được đóng gói lại thành lô vá riêng có hậu tố
    _rNN. Lô vá mang đúng những định danh bài mà lô gốc không sinh được bản ghi.
    Đếm phần thiếu của lô gốc mà bỏ qua lô vá thì mọi đợt có vá đều báo hỏng vượt
    ngưỡng, và --finish chặn trước cả bước nạp dù độ phủ thật đã đủ.

    Args:
        task_dir: Thư mục chứa packet và bảng ánh xạ.
        batch_id: Mã lô gốc đang xét, chưa có hậu tố vá.

    Returns:
        Tập định danh bài đã có bản ghi nhờ các lô vá của cùng đợt.
    """
    provided: set[str] = set()
    for map_path in sorted(glob.glob(str(task_dir / f"{batch_id}_r*.map.json"))):
        try:
            sibling = json.loads(Path(map_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        provided.update(str(v) for v in (sibling.get("index") or {}).values())
    return provided


def process_batch(batch_id: str, out_text: str, packet: dict, mapping: dict,
                  resolver: IntentResolver, reg, report: ResolveReport,
                  repaired_ids: set[str] | None = None,
                  default_provenance: tuple[str, str] | None = None) -> dict:
    """Xử lý một lô đầu ra của mô hình thành các tệp kết quả.

    Args:
        batch_id: Mã lô.
        out_text: Nội dung thô mô hình trả về.
        packet: Nội dung packet đã gửi cho mô hình.
        mapping: Bảng ánh xạ chỉ số cục bộ sang định danh bài.
        resolver: Bộ tra cứu định danh.
        reg: Danh mục thực thể.
        report: Bộ đếm thống kê tra cứu.
        repaired_ids: Định danh bài đã được lô vá của cùng đợt cung cấp. Bài nằm
            trong tập này không tính là thiếu, vì bản ghi của nó đã có trên đĩa.
        default_provenance: Cặp (provider, model) dùng khi lô không có tệp meta.
            Không truyền thì lô thiếu meta bị từ chối.

    Returns:
        Từ điển thống kê kết quả xử lý lô.
    """
    parsed = parse_and_validate(out_text, packet)
    broken = parsed.counters.get("broken", 0)
    by_index = {str(i): r for i, r in parsed.records.items()}
    index_map = mapping.get("index") or {}
    articles = {str(a.get("i")): a for a in (packet.get("a") or [])}

    L1_OUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    MENTIONS_DIR.mkdir(parents=True, exist_ok=True)

    repaired_ids = repaired_ids or set()
    l1_rows: list[dict] = []
    gold_rows: list[dict] = []
    mention_rows: list[dict] = []
    missing: list[str] = []
    gold_skipped: list[tuple[str, str]] = []

    meta_path = IN_DIR / f"{batch_id}.meta.json"
    batch_provider = batch_model = ""
    if meta_path.exists():
        try:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            batch_provider = meta_data.get("agent_provider") or ""
            batch_model = meta_data.get("model_used") or ""
        except (OSError, ValueError):
            pass
    if not (batch_provider and batch_model) and default_provenance:
        batch_provider, batch_model = default_provenance
    if not (batch_provider and batch_model):
        return {"batch_id": batch_id,
                "error": "thiếu meta provenance (agent_provider, model_used)",
                "expected": len(index_map), "owned": len(index_map), "repaired": 0,
                "records": 0, "invalid": {}, "counters": {}, "broken": 0,
                "missing": list(index_map), "l1": 0, "gold": 0, "mentions": 0,
                "gold_skipped": [], "parse_fail_rate": 1.0}

    for idx, article_id in index_map.items():
        rec = by_index.get(idx)
        if rec is None:
            # Bài đã có bản ghi nhờ lô vá thì không thiếu: đếm nó vào đây là lặp
            # lại đúng khoản đã trả bằng một lượt gọi khác.
            if str(article_id) not in repaired_ids:
                missing.append(idx)
            continue
        src = articles.get(idx) or {}
        title = src.get("t") or ""
        paragraphs = src.get("p") or []

        resolved = resolver.resolve_many(rec.get("e") or [], title=title, report=report)
        code_ids = {d["entity_id"] for d in reg.detect(title)}
        labels = reconcile(resolved, code_ids)

        l1_rows.append(build_l1_output(article_id, title, resolved, labels,
                                       agent_provider=batch_provider,
                                       model_used=batch_model))

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

    # Trần đếm hỏng là số bài lô này thật sự phải sinh, đã trừ phần lô vá gánh.
    owned = sum(1 for a in index_map.values() if str(a) not in repaired_ids)
    total = len(index_map)
    return {
        "batch_id": batch_id,
        "expected": total,
        "owned": owned,
        "repaired": total - owned,
        "records": len(parsed.records),
        "invalid": {str(i): codes for i, codes in parsed.errors.items()},
        "counters": parsed.counters,
        "broken": broken,
        "missing": missing,
        "l1": len(l1_rows),
        "gold": len(gold_rows),
        "mentions": len(mention_rows),
        "gold_skipped": gold_skipped,
        # Hai tập dưới phục vụ cổng toàn đợt ở main: một bài có bản ghi ở bất kỳ
        # lô nào (kể cả lô vá anh em, không chỉ con trực tiếp) là đã nhận.
        "received_ids": sorted({index_map[idx] for idx in by_index if idx in index_map}),
        "all_ids": sorted(set(index_map.values())),
        # Mẫu số là phần lô này thật sự phải sinh, không phải toàn bộ packet.
        # Lô vá đã trả giá cho phần nó gánh, nên tính phần ấy vào đây là tính hai lần.
        "parse_fail_rate": (len(missing) + broken) / owned if owned else 0.0,
    }


def drop_superseded_expanded(results: list[dict], outputs: list[str]) -> int:
    """Bỏ hàng bung cũ khi bài đã có bản ghi mới hơn ở lô vá khác.

    Vòng làm mới đẻ ra bản ghi thứ hai cho cùng bài (cũ từ packet trích ngắn,
    mới từ Silver đầy đủ). Tệp bung ra đĩa theo từng lô nên bản cũ vẫn nằm đó
    và cổng nạp sẽ loại nó vì trích dẫn không đối chiếu được vào thân mới —
    chặn oan cả đợt dù bản mới đã đạt. Giữ đúng một hàng mỗi bài: hàng của lô
    có đầu ra thô mới nhất. Đầu ra thô của mô hình không đụng tới nên vết kiểm
    toán còn nguyên. Không trùng thì không đụng tới tệp nào.

    Args:
        results: Thống kê từng lô của vòng bung hiện tại.
        outputs: Đường dẫn các tệp đầu ra thô vừa xử lý.

    Returns:
        Số hàng đã bỏ khỏi các tệp bung.
    """
    order: dict[str, tuple[float, str]] = {}
    for out_path in outputs:
        batch_id = Path(out_path).name.replace(".output.json", "")
        try:
            order[batch_id] = (Path(out_path).stat().st_mtime, batch_id)
        except OSError:
            continue
    by_batch: dict[str, list[tuple[str, dict]]] = {}
    for kind, filename, out_dir in (
            ("l1", ".output.json", L1_OUT_DIR),
            ("gold", ".output.json", GOLD_OUT_DIR),
            ("mentions", ".mentions.json", MENTIONS_DIR)):
        for r in results:
            path = out_dir / f"{r['batch_id']}{filename}"
            if not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and row.get("article_id"):
                    by_batch.setdefault(r["batch_id"], []).append((kind, row))
    if not any(len(items) > 0 for items in by_batch.values()):
        return 0
    seen: dict[str, tuple[float, str]] = {}
    for batch_id, items in by_batch.items():
        for _kind, row in items:
            aid = row["article_id"]
            stamp = order.get(batch_id, (0.0, batch_id))
            if aid not in seen or stamp > seen[aid]:
                seen[aid] = stamp
    dropped = 0
    for r in results:
        for kind, filename, out_dir in (
                ("l1", ".output.json", L1_OUT_DIR),
                ("gold", ".output.json", GOLD_OUT_DIR),
                ("mentions", ".mentions.json", MENTIONS_DIR)):
            path = out_dir / f"{r['batch_id']}{filename}"
            if not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            stamp = order.get(r["batch_id"], (0.0, r["batch_id"]))
            kept = [row for row in rows
                    if not (isinstance(row, dict) and row.get("article_id"))
                    or seen.get(row["article_id"]) == stamp]
            if len(kept) != len(rows):
                dropped += len(rows) - len(kept)
                path.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                if kind in r:
                    r[kind] = len(kept)
    return dropped


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh bung bản ghi gọn.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi đạt (chế độ đợt: tỷ lệ hỏng toàn đợt dưới ngưỡng),
        1 khi vượt ngưỡng hỏng, 2 khi không có việc.
    """
    ap = argparse.ArgumentParser(description="Bung bản ghi gọn thành hai lược đồ đầy đủ")
    ap.add_argument("source", nargs="?", default=str(IN_DIR),
                    help="Thư mục chứa đầu ra thô của mô hình")
    ap.add_argument("--task-dir", default=str(TASK_DIR), help="Thư mục chứa packet")
    ap.add_argument("--batch", help="Chỉ xử lý một lô cụ thể")
    ap.add_argument("--wave", help="Chỉ xử lý các lô của một đợt, gồm cả lô vá")
    ap.add_argument("--default-provider", help="Provider cho lô không có tệp meta, ví dụ dsh")
    ap.add_argument("--default-model", help="Mô hình cho lô không có tệp meta")
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
        repaired_ids = load_repair_ids(task_dir, batch_id)
        default_prov = ((args.default_provider, args.default_model or args.default_provider)
                        if args.default_provider else None)
        results.append(process_batch(batch_id, text, packet, mapping, resolver, reg,
                                     report, repaired_ids, default_prov))

    if not results:
        print("Không lô nào xử lý được.")
        return 2

    dropped = drop_superseded_expanded(results, outputs)
    if dropped:
        print(f"Đã bỏ {dropped} hàng bung cũ bị bản ghi mới hơn thay thế.")

    # Cổng toàn đợt: một bài có bản ghi ở bất kỳ lô nào là đã nhận. Đếm thiếu
    # theo lô cao nhất rồi chặn cả đợt là sai khi các lô vá chồng lấp thế hệ
    # (E1): bài thiếu ở lô cha nhưng đã có ở lô vá anh em vẫn bị tính hỏng.
    # Bảng theo lô giữ lại để soi, không dùng để chặn ở chế độ đợt.
    wave_ids: set[str] = set()
    wave_got: set[str] = set()
    for r in results:
        wave_ids.update(r.get("all_ids") or [])
        wave_got.update(r.get("received_ids") or [])
    wave_missing = sorted(wave_ids - wave_got)
    wave_rate = len(wave_missing) / len(wave_ids) if wave_ids else 0.0

    if args.json:
        print(json.dumps({"batches": results,
                          "resolve": report.summary(),
                          "wave_fail_rate": wave_rate,
                          "wave_missing": wave_missing}, ensure_ascii=False))
        return 0

    no_meta = [r["batch_id"] for r in results if r.get("error")]
    if no_meta:
        print(f"Lô thiếu meta provenance, không bung: {', '.join(no_meta)}")
        print("Ghi tệp meta cho lô, hoặc truyền --default-provider và --default-model.")
        return 1
    worst = max(r["parse_fail_rate"] for r in results)
    print("=" * 84)
    print(" 🧩  BUNG BẢN GHI GỌN THÀNH LƯỢC ĐỒ ĐẦY ĐỦ")
    print("=" * 84)
    print(f"{'lô':28} {'chờ':>5} {'nhận':>6} {'L1':>5} {'nội dung':>9} {'hỏng':>6} {'thiếu':>6} {'vá':>5}")
    print("-" * 90)
    for r in results:
        print(f"{r['batch_id']:28} {r['expected']:>5} {r['records']:>6} {r['l1']:>5} "
              f"{r['gold']:>9} {r['broken']:>6} {len(r['missing']):>6} "
              f"{r['repaired']:>5}")
    print("-" * 90)

    print("\nTỷ lệ tra cứu định danh theo nhóm:")
    for group, total, ok, rate in report.summary():
        note = "  (chưa có bảng tra, đúng thiết kế)" if group in GROUPS_WITHOUT_RESOLVER else ""
        print(f"  {group:5} {ok:>4}/{total:<4} {rate:>6.0%}{note}")

    skipped = [(r["batch_id"], s) for r in results for s in r["gold_skipped"]]
    if skipped:
        print(f"\nBài không dựng được phần nội dung: {len(skipped)}")
        for batch_id, (idx, reason) in skipped[:8]:
            print(f"  {batch_id} #{idx}: {reason}")

    invalid = [(r["batch_id"], i, c) for r in results for i, c in r["invalid"].items()]
    if invalid:
        print(f"\nBản ghi bị từ chối theo hợp đồng, chuyển sang vòng vá: {len(invalid)}")
        for batch_id, idx, codes in invalid[:8]:
            print(f"  {batch_id} #{idx}: {','.join(codes)}")

    print(f"\nTỷ lệ hỏng cao nhất trong đợt: {worst:.1%} "
          f"(ngưỡng dừng {args.fail_threshold:.0%})")
    gate = worst
    if args.wave:
        print(f"Tỷ lệ hỏng toàn đợt: {wave_rate:.1%} "
              f"({len(wave_missing)}/{len(wave_ids)} bài chưa có bản ghi "
              f"ở bất kỳ lô nào)")
        gate = wave_rate
    print("=" * 84)
    print("Bước tiếp: `l1_ingest.py data/agent_outputs_l1` rồi `agent_ingest.py data/agent_outputs`")
    return 1 if gate > args.fail_threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
