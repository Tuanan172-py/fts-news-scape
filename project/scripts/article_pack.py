"""Đóng gói bài đăng thành packet cho worker, kèm xếp ưu tiên và dự toán chi phí.

Mọi bài đều được xử lý đầy đủ cả tiêu đề lẫn nội dung; việc xếp tầng chỉ quyết định
**thứ tự chạy**, không quyết định độ sâu. Nhờ vậy một bài bị xếp thừa vào tầng ưu
tiên chỉ được xử lý sớm hơn chứ không tốn thêm token, nên bộ xếp hạng được phép
thiên về nhận rộng: thà nhận nhầm còn hơn bỏ sót bài mà người dùng đang theo dõi.

Packet bắt buộc ghi dạng gọn không thụt lề. Packet cũ ghi thụt lề khiến nội dung mỗi
bài dồn thành một dòng vật lý dài quá hai nghìn ký tự, vượt ngưỡng cắt dòng của công
cụ đọc, làm agent mất tin vào dữ liệu và tự mở vòng kiểm chứng tốn hàng trăm nghìn
token. Đây là nguyên nhân trực tiếp của vệt Gold 154 đến 300 nghìn token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.distill import (                      # noqa: E402
    DEFAULT_MAX_TOKENS_PER_ARTICLE,
    distill_stats,
    estimate_tokens,
)
from src.agent.entities import load_registry          # noqa: E402
from src.agent.prefix import (                        # noqa: E402
    SYSTEM_OVERHEAD_TOKENS,
    cached_prefix_tokens,
    persona_tokens,
)
from src.core.stdio import force_utf8_stdio           # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
DB_PATH = Path("C:/data/news-scape/monocle.db")
TASK_DIR = DATA_ROOT / "agent_tasks" / "article"

# Ba trần dưới đây là số thật của công cụ đọc trong DSH, đọc từ README của
# `dsh-tool-fs`: `readMaxLineLength` 2000 ký tự mỗi dòng, `readMaxBytes` 51.200 byte
# mỗi lần gọi, `readLimit` 2000 dòng mỗi lần gọi. Packet phải được viết sao cho phía
# điều phối đọc lại được nguyên vẹn, nếu không dữ liệu bị cắt cụt âm thầm — đúng loại
# sự cố đã đẻ ra vòng kiểm chứng tốn hàng trăm nghìn token ở vệt Gold.
READ_MAX_LINE_CHARS = 2000
READ_MAX_BYTES = 51_200
READ_MAX_LINES = 2000
LINE_SAFETY_MARGIN = 100

CONTEXT_WINDOW = 1_000_000

# Đo ngày 2026-09-21 trên 400 bản ghi thật gần nhất của mỗi bảng:
#   l1_outputs     trung bình   872 ký tự  ≈ 291 token, p90 370
#   agent_outputs  trung bình 1.946 ký tự  ≈ 649 token, p90 859
# Bản ghi hợp nhất của Article Lane mang cả hai phần nên nặng khoảng 900 token,
# p90 khoảng 1.200. Hằng số cũ để 300 vì nó được hiệu chuẩn trên riêng tầng L1;
# nó làm dự toán đầu ra hụt ba lần và che mất trần cắt cụt bên dưới.
DEFAULT_OUT_TOKENS_PER_ARTICLE = 900

# Mốc tham chiếu để ƯỚC LƯỢNG, **không** dùng để chia lô.
#
# 256.000 là `maxTokens` mặc định của DSH (`DEFAULT_MAX_TOKENS = 256e3` trong
# `dsh-llm-deepseek`), và con kế thừa của cha khi row không đặt gì. Nguồn:
# `docs/proposals/dsh-surface-verified-2026-09-18.md` §6.1–6.2, đọc từ mã nguồn DSH.
#
# Con số 40.000 trước đây **không** phải trần nhà cung cấp mà là giá trị dự án tự
# đặt ở `maxTokens` trong preset. Đã gỡ khỏi preset ngày 21/09. Một đợt trăm bài cần
# khoảng 90.000 token đầu ra, tức còn dư gần ba lần so với mặc định thật.
#
# DSH không có trần token hay chi phí nào theo phiên hay theo ngày. Các giới hạn số
# duy nhất của nó: `maxTokens` 256.000 mỗi request, `contextWindow` 1.000.000,
# compaction ở 0,8×, pruner 8.192 ký tự, spill 50.000 byte.
REFERENCE_COMPLETION_TOKENS = 256_000

# Tín hiệu vĩ mô khẩn: bài mang các từ này luôn vào tầng ưu tiên kể cả khi không
# khớp mã nào trong danh sách theo dõi, vì chúng tác động toàn thị trường.
_MACRO_URGENT_RE = re.compile(
    r"(?:ngân\s*hàng\s*nhà\s*nước|nhnn|lãi\s*suất|tỷ\s*giá|room\s*tín\s*dụng"
    r"|lạm\s*phát|cpi|gdp|thuế\s*quan|thuế\s*chống\s*bán\s*phá\s*giá|thuế\s*tự\s*vệ"
    r"|fed|fomc|nâng\s*hạng|ftse|msci|trái\s*phiếu\s*doanh\s*nghiệp)",
    re.IGNORECASE,
)


def get_db_connection() -> sqlite3.Connection:
    """Mở kết nối tới cơ sở dữ liệu vận hành.

    Returns:
        Kết nối SQLite tới `monocle.db`.
    """
    db_file = DB_PATH if DB_PATH.exists() else (DATA_ROOT / "monocle.db")
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    return conn


def watchlist_universe(reg) -> tuple[set[str], set[str]]:
    """Dựng tập thực thể được theo dõi và tập ngành liên quan tới chúng.

    Tập ngành là phần mở rộng có chủ đích cho việc nhận rộng: một bài nói về ngành
    thép vẫn đáng ưu tiên với người đang theo dõi một mã thép, dù bài không nhắc mã.

    Args:
        reg: Thể hiện `EntityRegistry` đã nạp đăng ký người dùng.

    Returns:
        Cặp gồm tập định danh thực thể được theo dõi và tập tên ngành liên quan.
    """
    watched: set[str] = set()
    for subs in (reg.subscriptions or {}).values():
        watched |= set(subs)

    industries: set[str] = set()
    for eid in watched:
        ent = reg.entities.get(eid) or {}
        attrs = ent.get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            if attrs.get(key):
                industries.add(str(attrs[key]).strip().lower())
    return watched, industries


def tier_of(title: str, reg, watched: set[str], industries: set[str]) -> tuple[int, str]:
    """Xếp một bài vào tầng ưu tiên theo nguyên tắc nhận rộng.

    Args:
        title: Tiêu đề bài viết.
        reg: Thể hiện `EntityRegistry`.
        watched: Tập định danh thực thể đang được theo dõi.
        industries: Tập tên ngành liên quan tới danh sách theo dõi.

    Returns:
        Cặp gồm số tầng (1 là ưu tiên cao nhất) và lý do xếp tầng.
    """
    detected = reg.detect(title or "")
    ids = {d["entity_id"] for d in detected}

    hit = ids & watched
    if hit:
        return 1, f"watchlist:{sorted(hit)[0]}"

    for d in detected:
        attrs = (reg.entities.get(d["entity_id"]) or {}).get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            val = str(attrs.get(key) or "").strip().lower()
            if val and val in industries:
                return 1, f"industry:{val}"

    if _MACRO_URGENT_RE.search(title or ""):
        return 1, "macro-urgent"

    return 2, "background"


def load_candidates(conn: sqlite3.Connection, *, date: str | None, limit: int,
                    only_pending: bool) -> list[sqlite3.Row]:
    """Lấy danh sách bài cần xử lý kèm đường dẫn gói dữ liệu tầng bạc.

    Args:
        conn: Kết nối cơ sở dữ liệu.
        date: Lọc theo ngày xuất bản YYYY-MM-DD, hoặc None để lấy mọi ngày.
        limit: Số bài tối đa.
        only_pending: Chỉ lấy bài chưa có kết quả nhận diện đạt chuẩn.

    Returns:
        Danh sách bản ghi bài viết.
    """
    sql = [
        "SELECT a.url_title_hash AS article_id, a.title, a.published_at,",
        "       a.source_domain, w.package_path",
        "FROM articles a",
        "JOIN work_items w ON w.article_id = a.url_title_hash",
        "WHERE w.package_path IS NOT NULL",
    ]
    params: list = []
    if only_pending:
        sql.append("  AND NOT EXISTS (SELECT 1 FROM l1_outputs o "
                   "WHERE o.article_id = a.url_title_hash AND o.dod_pass = 1)")
    if date:
        sql.append("  AND substr(a.published_at,1,10) = ?")
        params.append(date)
    sql.append("GROUP BY a.url_title_hash")
    # Khoá phụ `url_title_hash` không để cho đẹp: nó làm thứ tự bài trở nên tất định.
    # Bộ nhớ đệm của nhà cung cấp khớp theo tiền tố tính từ token 0, nên hai lần đóng
    # gói cùng một tập bài phải cho ra packet giống nhau từng byte thì lần chạy lại
    # mới trúng cache. Chỉ `published_at DESC` thì các bài trùng mốc thời gian đổi
    # chỗ tuỳ kế hoạch truy vấn, và mọi token sau bài đầu tiên bị đổi chỗ đều trượt.
    sql.append("ORDER BY a.published_at DESC, a.url_title_hash")
    sql.append("LIMIT ?")
    params.append(limit)
    return list(conn.execute("\n".join(sql), params))


def read_cleaned_text(package_path: str) -> str:
    """Đọc nội dung đã chuẩn hóa từ gói dữ liệu tầng bạc.

    Args:
        package_path: Đường dẫn gói, tương đối với thư mục dự án hoặc tuyệt đối.

    Returns:
        Nội dung bài viết, hoặc chuỗi rỗng khi không đọc được.
    """
    p = Path(package_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / package_path
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f) or {}).get("cleaned_text") or ""
    except (OSError, json.JSONDecodeError):
        return ""


def plan_calls(n_articles: int, *, batch_cap: int) -> list[int]:
    """Chia một đợt thành các lượt gọi, chia đều, chỉ theo trần người vận hành đặt.

    `--batch` là cổng chia duy nhất. Không có trần token nào can thiệp vào đây nữa:
    ngữ cảnh không phải ràng buộc (một đợt trăm bài chiếm khoảng 15% cửa sổ), còn
    trần đầu ra thì chưa đo được nên không đủ tư cách làm luật chia lô.

    Chia đều thay vì cắt tràn, vì các lượt chạy song song nên đợt chỉ xong khi lượt
    dài nhất xong; một lượt lẻ rất ngắn không rút ngắn được gì.

    Args:
        n_articles: Số bài của cả đợt.
        batch_cap: Trần số bài mỗi lượt do người vận hành đặt.

    Returns:
        Danh sách số bài của từng lượt, cộng lại đúng bằng `n_articles`.
    """
    if n_articles <= 0:
        return []
    cap = max(1, batch_cap)
    n_calls = max(1, math.ceil(n_articles / cap))
    base, extra = divmod(n_articles, n_calls)
    return [base + (1 if i < extra else 0) for i in range(n_calls)]


def write_packet(batch_id: str, items: list[dict], mapping: dict,
                 out_dir: Path) -> tuple[Path, Path, dict]:
    """Ghi packet ra đĩa ở dạng đọc lại được nguyên vẹn, kèm bảng ánh xạ chỉ số.

    Packet được ghi **xuống dòng theo từng phần tử** thay vì dồn một dòng. Lý do:
    công cụ đọc cắt mỗi dòng ở 2.000 ký tự, nên một tệp JSON gọn nằm trọn trên một
    dòng sẽ bị cắt mất gần hết. Ghi mỗi đoạn văn một dòng thì dòng dài nhất bằng đúng
    đoạn dài nhất, mà đo trên 4.493 đoạn thật thì đoạn dài nhất chỉ 954 ký tự.

    Args:
        batch_id: Mã lô.
        items: Danh sách bài đã đóng gói.
        mapping: Bảng ánh xạ chỉ số cục bộ sang định danh bài.
        out_dir: Thư mục đích.

    Returns:
        Bộ ba gồm đường dẫn packet, đường dẫn bảng ánh xạ và số liệu ngân sách đọc.

    Raises:
        ValueError: Khi packet có dòng vượt ngưỡng cắt dòng của công cụ đọc.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "d": datetime.now().strftime("%Y-%m-%d"),
        "n": len(items),
        "a": items,
    }
    text = json.dumps(packet, ensure_ascii=False, indent=1)

    lines = text.splitlines()
    longest = max((len(line) for line in lines), default=0)
    limit = READ_MAX_LINE_CHARS - LINE_SAFETY_MARGIN
    if longest > limit:
        raise ValueError(
            f"packet {batch_id} có dòng dài {longest} ký tự, vượt ngưỡng an toàn {limit}. "
            "Công cụ đọc sẽ cắt cụt dòng này và phía điều phối nhận dữ liệu thiếu. "
            "Hạ MAX_PARAGRAPH_CHARS trong src/agent/distill.py rồi đóng gói lại."
        )

    packet_path = out_dir / f"{batch_id}.task.json"
    packet_path.write_text(text, encoding="utf-8")

    map_path = out_dir / f"{batch_id}.map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    size = len(text.encode("utf-8"))
    budget = {
        "bytes": size,
        # Băm của packet: bằng chứng kiểm được cho tính tất định. Đóng gói lại cùng
        # một tập bài mà băm đổi nghĩa là lần chạy lại sẽ trượt bộ nhớ đệm.
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "lines": len(lines),
        "longest_line": longest,
        "windows": read_windows(lines),
    }
    budget["read_calls"] = len(budget["windows"])
    return packet_path, map_path, budget


def read_windows(lines: list[str]) -> list[list[int]]:
    """Chia tệp thành các cửa sổ dòng mà mỗi cửa sổ đọc trọn trong một lần gọi.

    Công cụ đọc chặn ở 51.200 byte và 2.000 dòng cho mỗi lần gọi, nên một packet
    trăm bài phải đọc làm nhiều lần. Việc chia cửa sổ được tính sẵn ở đây để chương
    trình điều phối chỉ việc lặp theo danh sách, không phải đoán ngưỡng lúc chạy.
    Các lần đọc này nằm trong cùng một chương trình nên **không tốn thêm bước nào**
    của mô hình.

    Args:
        lines: Danh sách dòng của tệp packet.

    Returns:
        Danh sách cặp `[dòng bắt đầu tính từ 1, số dòng]`.
    """
    budget = READ_MAX_BYTES - 4096          # chừa chỗ cho khung bao và số dòng
    windows: list[list[int]] = []
    start = 1
    used = 0
    count = 0
    for idx, line in enumerate(lines, start=1):
        cost = len(line.encode("utf-8")) + 12
        if count and (used + cost > budget or count >= READ_MAX_LINES):
            windows.append([start, count])
            start = idx
            used = 0
            count = 0
        used += cost
        count += 1
    if count:
        windows.append([start, count])
    return windows or [[1, 1]]


def histogram(values: list[int], *, buckets: int = 6) -> list[str]:
    """Dựng biểu đồ phân bố dạng văn bản cho số token mỗi bài.

    Args:
        values: Danh sách số token của từng bài.
        buckets: Số khoảng chia.

    Returns:
        Danh sách dòng biểu đồ.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [f"  {lo:>5} token │ {'█' * 40} {len(values)}"]
    width = (hi - lo) / buckets
    lines = []
    for b in range(buckets):
        start = lo + width * b
        end = start + width
        n = sum(1 for v in values if (start <= v < end or (b == buckets - 1 and v == hi)))
        bar = "█" * int(40 * n / len(values)) if values else ""
        lines.append(f"  {int(start):>5}-{int(end):<5} │ {bar} {n}")
    return lines


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh đóng gói bài đăng.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi đóng gói được, 2 khi không có bài nào thoả điều kiện.
    """
    ap = argparse.ArgumentParser(description="Đóng gói bài đăng thành packet cho worker")
    ap.add_argument("--wave", default=datetime.now().strftime("%Y%m%dT%H%M"),
                    help="Mã đợt, dùng làm tiền tố tên lô")
    ap.add_argument("--batch", type=int, default=100, help="Số bài mỗi lô")
    ap.add_argument("--limit", type=int, default=300, help="Tổng số bài tối đa của đợt")
    ap.add_argument("--date", help="Chỉ lấy bài xuất bản trong ngày YYYY-MM-DD")
    ap.add_argument("--today", action="store_true", help="Tương đương --date hôm nay")
    ap.add_argument("--all-articles", action="store_true",
                    help="Lấy cả bài đã có kết quả nhận diện đạt chuẩn")
    ap.add_argument("--max-tokens-per-article", type=int,
                    default=DEFAULT_MAX_TOKENS_PER_ARTICLE,
                    help="Trần token phần nội dung mỗi bài")
    ap.add_argument("--out-tokens-per-article", type=int,
                    default=DEFAULT_OUT_TOKENS_PER_ARTICLE,
                    help="Cỡ bản ghi đầu ra mỗi bài, dùng để chia lượt gọi")
    ap.add_argument("--out-dir", default=str(TASK_DIR), help="Thư mục ghi packet")
    ap.add_argument("--json", action="store_true", help="Xuất mô tả đợt dạng JSON")
    args = ap.parse_args(argv)

    date = args.date or (datetime.now().strftime("%Y-%m-%d") if args.today else None)

    conn = get_db_connection()
    rows = load_candidates(conn, date=date, limit=args.limit,
                           only_pending=not args.all_articles)
    conn.close()
    if not rows:
        print("Không có bài nào thoả điều kiện. Kiểm lại --date hoặc hàng đợi work_items.")
        return 2

    reg = load_registry()
    watched, industries = watchlist_universe(reg)

    packed: list[dict] = []
    for r in rows:
        text = read_cleaned_text(r["package_path"])
        if not text:
            continue
        stats = distill_stats(text, max_tokens=args.max_tokens_per_article)
        if not stats["paragraphs"]:
            continue
        tier, reason = tier_of(r["title"], reg, watched, industries)
        packed.append({
            "article_id": r["article_id"],
            "title": r["title"] or "",
            "paragraphs": stats["paragraphs"],
            "tokens": stats["tokens_after"] + estimate_tokens(r["title"] or ""),
            "tier": tier,
            "reason": reason,
            "domain": r["source_domain"],
        })

    if not packed:
        print("Có bài nhưng không đọc được nội dung nào. Kiểm lại work_packages trên đĩa.")
        return 2

    # Tầng ưu tiên chạy trước; trong cùng tầng giữ nguyên thứ tự mới nhất trước.
    # `sort` của Python ổn định và truy vấn đã sắp tất định, nên thứ tự cuối cùng chỉ
    # phụ thuộc dữ liệu chứ không phụ thuộc lần chạy — điều kiện để lần đóng gói lại
    # cho ra packet giống hệt và trúng bộ nhớ đệm.
    packed.sort(key=lambda a: a["tier"])

    # Tiền tố tĩnh gồm CẢ phần harness tự nối vào (AGENTS.md, section tool/SDK), chứ
    # không chỉ phần persona dự án tự dán. Cả hai đều đứng trước packet và đều tĩnh,
    # nên cả hai đều trúng bộ nhớ đệm; đếm thiếu phần harness làm `est_hit` hụt khoảng
    # 4.800 token mỗi lượt và khiến số dự toán không đối chiếu được với `cacheRead`
    # thật trong sổ cái.
    pfx = cached_prefix_tokens()
    chunk_cap = max(1, args.batch)

    # Chia đều thay vì cắt tràn. Cắt tràn để lại một lượt lẻ rất ngắn, mà các lượt
    # chạy song song nên đợt chỉ xong khi lượt dài nhất xong: lượt lẻ không rút
    # ngắn được gì, chỉ làm lệch khối lượng giữa các lượt.
    sizes = plan_calls(len(packed), batch_cap=args.batch)

    # Đợt một lô không có lượt hâm bộ nhớ đệm: không có lô thứ hai để dùng lại tiền
    # tố, nên lượt hâm chỉ dời đúng khoản token miss ấy sang một request khác rồi
    # tính thêm một bản ghi đầu ra. Lô duy nhất tự trả giá token mới cho tiền tố.
    warmed = len(sizes) >= 2

    batches: list[dict] = []
    out_dir = Path(args.out_dir)
    cursor = 0
    seq = 1
    for size in sizes:
        chunk = packed[cursor:cursor + size]

        batch_id = f"article_{args.wave}_{seq:02d}"
        items = [{"i": i, "t": a["title"], "p": a["paragraphs"]}
                 for i, a in enumerate(chunk)]
        mapping = {
            "batch_id": batch_id,
            "wave": args.wave,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "index": {str(i): a["article_id"] for i, a in enumerate(chunk)},
            "tier": {str(i): a["tier"] for i, a in enumerate(chunk)},
            "reason": {str(i): a["reason"] for i, a in enumerate(chunk)},
        }
        packet_path, map_path, budget = write_packet(batch_id, items, mapping, out_dir)

        est_in = pfx + sum(a["tokens"] for a in chunk)
        est_out = len(chunk) * args.out_tokens_per_article
        batches.append({
            "batch_id": batch_id,
            "path": str(packet_path),
            "map": str(map_path),
            "n": len(chunk),
            "tier1": sum(1 for a in chunk if a["tier"] == 1),
            "est_miss": est_in - pfx,
            "est_hit": pfx if warmed else 0,
            "est_out": est_out,
            "est_ctx_peak": est_in + est_out,
            "bytes": budget["bytes"],
            "sha256": budget["sha256"],
            "read_calls": budget["read_calls"],
            "longest_line": budget["longest_line"],
            "windows": budget["windows"],
        })
        cursor += len(chunk)
        seq += 1

    summary = {
        "wave": args.wave,
        # Mốc thời gian này là điểm neo để sổ cái quy kết chi phí: chỉ những phiên
        # DSH sinh ra SAU khi đóng gói mới thuộc về đợt. Lấy mốc rộng hơn sẽ gộp
        # nhầm cả phiên không liên quan và thổi phồng con số chi phí mỗi bài.
        "created_epoch": datetime.now().timestamp(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "articles": len(packed),
        "batches": batches,
        "tier1": sum(b["tier1"] for b in batches),
        "prefix_tokens": pfx,
        "persona_tokens": persona_tokens(),
        "system_overhead_tokens": SYSTEM_OVERHEAD_TOKENS,
        # Lượt hâm bộ nhớ đệm đi trước mọi lô: nó trả giá token mới cho phần tiền tố
        # đúng một lần, đổi lại mọi lô sau đều trúng cache và không lô nào phải chờ.
        "est_warm_miss": pfx,
        "warmed": warmed,
        "per_call": chunk_cap,
        "out_tokens_per_article": args.out_tokens_per_article,
        "reference_completion_tokens": REFERENCE_COMPLETION_TOKENS,
        "est_miss_total": sum(b["est_miss"] for b in batches) + pfx,
        "est_hit_total": sum(b["est_hit"] for b in batches),
        "est_out_total": sum(b["est_out"] for b in batches),
    }
    summary["est_quota_total"] = (summary["est_miss_total"] + summary["est_hit_total"]
                                  + summary["est_out_total"])

    manifest = Path(args.out_dir) / f"wave_{args.wave}.json"
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    summary["manifest"] = str(manifest)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    tokens = [a["tokens"] for a in packed]
    print("=" * 84)
    print(f" 📦  ĐÓNG GÓI ĐỢT {args.wave}")
    print("=" * 84)
    lot = (f"{len(batches)} lượt gọi song song trong MỘT bước điều phối"
           if len(batches) > 1 else "MỘT lượt gọi duy nhất")
    print(f"Bài đóng gói : {len(packed):,} ({summary['tier1']:,} tầng ưu tiên) → {lot}")
    cache_note = ("mọi lô trúng cache nhờ lượt hâm đi trước" if warmed
                  else "một lô nên không hâm; lô này trả giá token mới")
    print(f"Prefix tĩnh  : {pfx:,} token = persona {persona_tokens():,} + harness "
          f"{SYSTEM_OVERHEAD_TOKENS:,} ({cache_note})")
    worst_out = max((b["est_out"] for b in batches), default=0)
    print(f"Chia lô      : chỉ theo --batch = {args.batch}. Không trần token nào "
          f"can thiệp.")
    print(f"Đầu ra ước   : {worst_out:,} token cho lượt nặng nhất "
          f"(bản ghi {args.out_tokens_per_article} token/bài)")
    if worst_out > REFERENCE_COMPLETION_TOKENS:
        print(f"               ⓘ  Vượt mốc tham chiếu "
              f"{REFERENCE_COMPLETION_TOKENS:,}. Đây là THÔNG TIN, không phải chặn.")
        print(f"               Nếu lượt nào trả về thiếu bài, chạy "
              f"`article_run.py --wave <mã> --repair` để đóng gói lại đúng phần "
              f"thiếu.")
    print()
    print(f"{'lô':26} {'bài':>4} {'ưu tiên':>8} {'miss':>9} {'out':>7} "
          f"{'ctx đỉnh':>9} {'KB':>6} {'đọc':>4}")
    print("-" * 84)
    for b in batches:
        print(f"{b['batch_id']:26} {b['n']:>4} {b['tier1']:>8} "
              f"{b['est_miss']:>9,} {b['est_out']:>7,} "
              f"{b['est_ctx_peak'] / CONTEXT_WINDOW:>8.1%} "
              f"{b['bytes'] / 1024:>6.0f} {b['read_calls']:>4}")
    print("-" * 84)
    print(f"Dự toán đợt  : quota {summary['est_quota_total']:,} token "
          f"(miss {summary['est_miss_total']:,} · hit {summary['est_hit_total']:,} · "
          f"out {summary['est_out_total']:,})")
    print()
    print("Phân bố token mỗi bài:")
    for line in histogram(tokens):
        print(line)

    reads = sum(b["read_calls"] for b in batches)
    longest = max(b["longest_line"] for b in batches)
    print()
    print(f"Ngân sách đọc: {reads} lần gọi `read` cho cả đợt "
          f"(mỗi lần tối đa {READ_MAX_BYTES // 1024} KB) · dòng dài nhất {longest} ký tự "
          f"trên trần {READ_MAX_LINE_CHARS}")
    if reads > len(batches):
        print("  Lô nào cần hơn một lần đọc thì phía điều phối phải phân trang bằng "
              "`offset`/`limit` ngay trong cùng một chương trình; việc này KHÔNG tốn "
              "thêm bước nào của mô hình.")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
