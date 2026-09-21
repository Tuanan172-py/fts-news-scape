"""Ghi và báo cáo số đo token thật của runtime DSH vào sổ cái `token_ledger`.

Sổ cái này thay thế hoàn toàn các hằng số ước lượng cũ. Hai vệt audit thật cho thấy
định mức khai báo trong `registry.yaml` lệch thực tế 21 đến 41 lần, nên mọi con số
chi phí từ nay phải đến từ đây chứ không từ phép nhân định mức.

Mỗi dòng sổ cái ghi đồng thời hai thước đo và luôn nói rõ đang dùng thước nào:
`quota_tokens` là tổng token tính vào hạn mức tài khoản, còn `billed_usd` là tiền.
Hai thước này lệch nhau rất xa vì token trúng bộ nhớ đệm rẻ hơn token mới 50 lần.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.prefix import cached_prefix_tokens    # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.telemetry.dsh_usage import (                # noqa: E402
    is_peak,
    load_pricing,
    wave_usage,
)

force_utf8_stdio()

HARNESS_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "harness.db",
)

# Mô tả đợt nằm cạnh packet; đọc từ đây để biết một đợt có bao nhiêu LƯỢT GỌI
# worker, thay vì suy từ số phiên DSH vốn gồm cả phiên Conductor.
TASK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "agent_tasks", "article",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS token_ledger (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    wave             TEXT,
    batch_id         TEXT,
    agent_id         TEXT    NOT NULL DEFAULT 'article-processor',
    n_items          INTEGER NOT NULL DEFAULT 0,
    n_sessions       INTEGER NOT NULL DEFAULT 0,
    miss_tokens      INTEGER NOT NULL DEFAULT 0,
    hit_tokens       INTEGER NOT NULL DEFAULT 0,
    out_tokens       INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER,
    quota_tokens     INTEGER NOT NULL DEFAULT 0,
    turns_max        INTEGER NOT NULL DEFAULT 0,
    ctx_peak         INTEGER NOT NULL DEFAULT 0,
    ctx_pct          REAL    NOT NULL DEFAULT 0,
    est_miss         INTEGER,
    est_out          INTEGER,
    billed_usd       REAL    NOT NULL DEFAULT 0,
    peak_window      INTEGER NOT NULL DEFAULT 0,
    note             TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_ledger_wave ON token_ledger(wave);
CREATE INDEX IF NOT EXISTS idx_token_ledger_ts   ON token_ledger(ts);
"""


def latest_snapshots(rows: list) -> list:
    """Giữ lại ảnh chụp mới nhất của mỗi đợt, bỏ các ảnh chụp cũ hơn của cùng đợt.

    `append` ghi một ảnh chụp **tích luỹ** mỗi lần chạy, không phải phần tăng thêm:
    chạy lại cho cùng một đợt khi các phiên con lần lượt kết thúc thì dòng sau chứa
    trọn dòng trước. Đợt W2 có bốn dòng như vậy, và cộng thẳng chúng cho ra 800 bài
    cho một đợt 200 bài.

    Quy ước lấy dòng mới nhất đã có sẵn ở `estimate_wave.py`; hàm này để mọi công cụ
    dùng chung đúng một quy ước, thay vì mỗi nơi tự cộng một kiểu rồi báo số khác nhau
    về cùng một đợt.

    Args:
        rows: Các dòng sổ cái, đã sắp theo thứ tự ghi tăng dần.

    Returns:
        Danh sách dòng còn lại sau khi khử ảnh chụp cũ.
    """
    latest: dict[tuple, object] = {}
    for r in rows:
        latest[(r["wave"], r["batch_id"], r["agent_id"])] = r
    return list(latest.values())


def worker_calls(wave: str | None) -> int | None:
    """Số lượt gọi worker thật của một đợt, đọc từ mô tả đợt trên đĩa.

    Args:
        wave: Mã đợt.

    Returns:
        Số lượt gọi worker, hoặc None khi không có mô tả đợt.
    """
    if not wave:
        return None
    path = os.path.join(TASK_DIR, f"wave_{wave}.json")
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return None
    n = len(m.get("batches") or [])
    if not n:
        return None
    return n + (1 if m.get("warmed") else 0)


def cache_shortfall(cache_read: int, n_sessions: int, prefix_tokens: int,
                    calls: int | None = None) -> tuple[int, int]:
    """Đối chiếu số token trúng bộ nhớ đệm thật với số tối thiểu phải trúng.

    Mỗi lượt gọi worker gửi cùng một tiền tố tĩnh. Lượt đầu ghi cache, mọi lượt sau
    phải đọc lại xấp xỉ trọn tiền tố ấy ở giá trúng cache. Sàn tối thiểu vì vậy là
    `tiền tố × (số lượt gọi worker − 1)`; thấp hơn sàn nghĩa là tiền tố đã lệch giữa
    các lượt, và phần lệch bị tính giá token mới, đắt hơn năm mươi lần.

    Đây là phép kiểm duy nhất phát hiện được cache trượt. Tỷ lệ trúng cache gộp cả
    đợt **không** phát hiện được: nó vẫn cao khi các lượt lặp bước, ngay cả lúc tiền
    tố trượt sạch.

    **Đếm theo lượt gọi worker, không theo số phiên.** Một đợt hai lô có tới bốn
    phiên: phiên Conductor, lượt hâm, và hai lô. Phiên Conductor mang persona khác
    và bộ tool khác nên nó **không** đọc tiền tố của worker; tính nó vào sàn là đòi
    một khoản cache không bao giờ tồn tại, và cảnh báo sẽ kêu oan ở mọi đợt bình
    thường — đúng kiểu cảnh báo tự huỷ giá trị của chính nó.

    Args:
        cache_read: Số token trúng cache đo được của cả đợt.
        n_sessions: Số phiên DSH của đợt, chỉ dùng khi không biết số lượt gọi.
        prefix_tokens: Kích thước tiền tố tĩnh.
        calls: Số lượt gọi worker thật. Bỏ trống thì suy từ số phiên, và khi ấy sàn
            chỉ là ước lượng thô.

    Returns:
        Cặp gồm sàn tối thiểu và phần hụt so với sàn; hụt bằng 0 là đạt.
    """
    n = calls if calls else max(0, n_sessions - 1)
    expected = max(0, prefix_tokens) * max(0, n - 1)
    return expected, max(0, expected - max(0, cache_read))


def connect(db_path: str = HARNESS_DB) -> sqlite3.Connection:
    """Mở kết nối sổ cái và bảo đảm lược đồ bảng đã tồn tại.

    Args:
        db_path: Đường dẫn tệp `harness.db`.

    Returns:
        Kết nối SQLite đã sẵn sàng dùng.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def cmd_init(args: argparse.Namespace) -> int:
    """Tạo bảng sổ cái nếu chưa có.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0.
    """
    conn = connect(args.db)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(token_ledger)")]
    conn.close()
    print(f"✅ Bảng token_ledger sẵn sàng tại {args.db} ({len(cols)} cột).")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    """Gộp số đo của các phiên phát sinh sau một mốc và ghi thành một dòng sổ cái.

    Chi phí của agent con không nằm trong số đo phiên cha vì mỗi con là một Session
    riêng, nên hàm này quét toàn bộ phiên mới thay vì chỉ đọc phiên điều phối.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi ghi được, 2 khi không tìm thấy phiên nào trong khoảng.
    """
    since = args.since if args.since is not None else time.time() - args.window_min * 60
    wave = wave_usage(since, cwd_filter=args.cwd_filter, with_reasoning=not args.no_reasoning)

    if not wave.sessions:
        print(f"⚠️  Không có phiên DSH nào sửa đổi sau mốc đã cho "
              f"({datetime.fromtimestamp(since):%Y-%m-%d %H:%M:%S}). Không ghi gì.")
        return 2

    pricing = load_pricing()
    peak = args.peak if args.peak is not None else is_peak(pricing=pricing)
    usd = wave.usd(peak=peak, pricing=pricing)
    ctx_peak = max((s.pressure_tokens for s in wave.sessions), default=0)
    ctx_pct = max((s.pressure_ratio for s in wave.sessions), default=0.0)
    turns_max = max((s.turns for s in wave.sessions), default=0)

    conn = connect(args.db)
    conn.execute(
        """INSERT INTO token_ledger
           (ts, wave, batch_id, agent_id, n_items, n_sessions, miss_tokens, hit_tokens,
            out_tokens, reasoning_tokens, quota_tokens, turns_max, ctx_peak, ctx_pct,
            est_miss, est_out, billed_usd, peak_window, note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         args.wave, args.batch, args.agent, args.items, len(wave.sessions),
         wave.uncached_input, wave.cache_read, wave.output,
         wave.reasoning_tokens if wave.reasoning_known else None,
         wave.quota_tokens, turns_max, ctx_peak, round(ctx_pct, 4),
         args.est_miss, args.est_out, round(usd, 6), int(peak), args.note),
    )
    conn.commit()
    conn.close()

    per_item = wave.quota_tokens / args.items if args.items else 0
    print(f"✅ Đã ghi sổ cái: wave={args.wave or '-'} batch={args.batch or '-'} "
          f"({len(wave.sessions)} phiên, {args.items} bài)")
    print(f"   quota {wave.quota_tokens:,} token "
          f"(miss {wave.uncached_input:,} · hit {wave.cache_read:,} · out {wave.output:,})")
    if wave.reasoning_known:
        flag = "" if wave.reasoning_tokens == 0 else "  ⚠️ effort chưa tắt?"
        print(f"   reasoning {wave.reasoning_tokens:,} token{flag}")
    else:
        print("   reasoning: không đọc được nhật ký JSONL (không chặn, số khác vẫn đúng)")
    if args.items:
        print(f"   {per_item:,.0f} token/bài · ${usd:.4f} ({'peak' if peak else 'off-peak'})")
    if turns_max > 1:
        print(f"   ⚠️ turns_max={turns_max}: có phiên chạy quá 1 bước, soi lại persona worker")

    pfx = args.prefix_tokens or cached_prefix_tokens()
    calls = args.worker_calls or worker_calls(args.wave)
    expected_hit, shortfall = cache_shortfall(wave.cache_read, len(wave.sessions), pfx,
                                              calls=calls)
    basis = (f"{calls} luot goi worker theo mo ta dot" if calls
             else f"{len(wave.sessions)} phien, tru phien dieu phoi")
    if expected_hit:
        table = pricing["models"]["deepseek-flash"]["peak" if peak else "off_peak"]
        gap_usd = shortfall * (table["input_cache_miss"] - table["input_cache_hit"]) / 1e6
        if shortfall:
            print(f"   ⚠️ bộ nhớ đệm TRƯỢT: hit {wave.cache_read:,} token, sàn tối thiểu "
                  f"{expected_hit:,} (tiền tố {pfx:,} × số lượt sau lượt đầu; "
                  f"cơ sở: {basis}) — hụt {shortfall:,} token ≈ ${gap_usd:.4f}")
            print(f"      Kiểm theo thứ tự: (1) `build_article_prefix.py --check` — "
                  f"persona trong preset có còn khớp prefix từng byte không; (2) trong "
                  f"đợt có đổi tool set, model hay reasoningEffort không; (3) phiên nào "
                  f"chạm ngưỡng nén 80% thì vùng surface đã bị viết lại.")
        else:
            print(f"   ✅ bộ nhớ đệm trúng: hit {wave.cache_read:,} token so với sàn "
                  f"{expected_hit:,}")

    warn = float((pricing.get("watch_thresholds") or {}).get("tokens_per_article_warn", 1500))
    if args.items and per_item > warn:
        print(f"   ⚠️ {per_item:,.0f} token/bài vượt ngưỡng cảnh báo {warn:,.0f}.")
        print(f"      Hai nguyên nhân hay gặp, kiểm theo thứ tự: (1) mốc --since quá rộng nên "
              f"gộp nhầm phiên DSH khác đang mở song song — đợt này gộp {len(wave.sessions)} "
              f"phiên; (2) distillation cho packet quá dày, soi histogram của article_pack.")
    return 0


def _fmt_row(r: sqlite3.Row) -> str:
    """Định dạng một dòng sổ cái thành chuỗi hiển thị.

    Args:
        r: Dòng dữ liệu đọc từ bảng sổ cái.

    Returns:
        Chuỗi một dòng đã canh cột.
    """
    per = (r["quota_tokens"] / r["n_items"]) if r["n_items"] else 0
    reasoning = "—" if r["reasoning_tokens"] is None else f"{r['reasoning_tokens']:,}"
    return (f"{r['ts'][:19]:20} {str(r['wave'] or '-'):>6} {r['n_items']:>6} "
            f"{r['miss_tokens']:>10,} {r['hit_tokens']:>12,} {r['out_tokens']:>9,} "
            f"{reasoning:>9} {per:>9,.0f} {r['turns_max']:>5} ${r['billed_usd']:>8.4f}")


def cmd_report(args: argparse.Namespace) -> int:
    """In báo cáo sổ cái theo đợt hoặc theo ngày.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0.
    """
    conn = connect(args.db)
    sql = "SELECT * FROM token_ledger"
    params: list = []
    where = []
    if args.wave:
        where.append("wave = ?")
        params.append(args.wave)
    if args.date:
        where.append("substr(ts,1,10) = ?")
        params.append(args.date)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    rows = list(conn.execute(sql, params))
    conn.close()

    print("=" * 110)
    print(" 🪙  SỔ CÁI TOKEN — SỐ THẬT TỪ RUNTIME DSH")
    print("=" * 110)
    if not rows:
        print("Chưa có dòng nào. Chạy `token_ledger.py append` sau một wave để ghi.")
        print("=" * 110)
        return 0

    print(f"{'thời điểm':20} {'wave':>6} {'bài':>6} {'miss':>10} {'hit':>12} "
          f"{'out':>9} {'reason':>9} {'tok/bài':>9} {'lượt':>5} {'USD':>9}")
    print("-" * 110)
    for r in rows:
        print(_fmt_row(r))

    # Cộng trên ảnh chụp mới nhất của mỗi đợt. Bảng bên trên vẫn in đủ mọi dòng vì
    # đó là sổ cái và người vận hành cần thấy nguyên trạng, nhưng phần cộng thì không
    # được đếm một đợt nhiều lần.
    unique = latest_snapshots(list(reversed(rows)))
    tot_items = sum(r["n_items"] for r in unique)
    tot_quota = sum(r["quota_tokens"] for r in unique)
    tot_usd = sum(r["billed_usd"] for r in unique)
    tot_miss = sum(r["miss_tokens"] for r in unique)
    tot_hit = sum(r["hit_tokens"] for r in unique)
    print("-" * 110)
    dropped = len(rows) - len(unique)
    note = f" (bỏ {dropped} ảnh chụp cũ của cùng đợt)" if dropped else ""
    print(f"CỘNG {len(unique)} đợt{note} · {tot_items:,} bài · "
          f"quota {tot_quota:,} token · ${tot_usd:.4f}")
    if tot_items:
        print(f"Trung bình {tot_quota / tot_items:,.0f} token/bài")
    if tot_miss + tot_hit:
        print(f"Tỷ lệ trúng cache {tot_hit / (tot_miss + tot_hit):.1%}")
    print("=" * 110)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Đối soát sáu luật kế toán trên dữ liệu phiên thật.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát 0 khi mọi luật kiểm được đều đạt, 1 khi có luật sai.
    """
    from src.telemetry.dsh_usage import find_session_log, iter_sessions, message_usage

    sessions = iter_sessions(args.cwd_filter)
    if not sessions:
        print("Không có phiên nào để đối soát.")
        return 0

    s = sessions[0]
    log = find_session_log(s.session_id)
    rows = message_usage(log) if log else []

    print("=" * 78)
    print(f" 🔍  ĐỐI SOÁT LUẬT KẾ TOÁN — phiên {s.session_id[:36]}")
    print("=" * 78)
    ok = True

    print(f"L1 · inputTokens là phần CHƯA cache, không phải kích thước prompt")
    print(f"     uncached {s.uncached_input:,} so với hit {s.cache_read:,} "
          f"(nếu đọc nhầm sẽ hụt ~{(s.cache_read / max(s.uncached_input, 1)):.0f} lần)")

    if rows:
        bad = [r for r in rows
               if r["input_tokens"] + r["cache_read_tokens"] + r["output_tokens"]
               != r["total_tokens"]]
        status = "ĐẠT" if not bad else f"SAI ở {len(bad)}/{len(rows)} dòng"
        ok = ok and not bad
        print(f"L2 · in + hit + out == total cho từng request: {status}")

        sub = [r for r in rows if r["reasoning_tokens"] > r["output_tokens"]]
        ok = ok and not sub
        print(f"L3 · reasoning là tập con của output: "
              f"{'ĐẠT' if not sub else f'SAI ở {len(sub)} dòng'}")
    else:
        print("L2 · bỏ qua: không giải nén được nhật ký JSONL")
        print("L3 · bỏ qua: không giải nén được nhật ký JSONL")

    print(f"L4 · cacheWrite luôn 0 với adapter DeepSeek: "
          f"{'ĐẠT' if s.cache_write == 0 else f'SAI ({s.cache_write:,})'}")
    ok = ok and s.cache_write == 0

    print("L5 · DSH không lưu giá; tiền tính từ config/token_pricing.yaml: ĐẠT theo thiết kế")
    print(f"L6 · surface {s.surface_tokens:,} <= pressure {s.pressure_tokens:,} "
          f"(surface không gồm tools, pressure không gồm output)")
    print("=" * 78)
    print("KẾT LUẬN:", "mọi luật kiểm được đều ĐẠT" if ok else "CÓ LUẬT SAI, xem ở trên")
    return 0 if ok else 1


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh của sổ cái token.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát của lệnh con được chọn.
    """
    ap = argparse.ArgumentParser(description="Sổ cái token đọc số thật từ runtime DSH")
    ap.add_argument("--db", default=HARNESS_DB, help="Đường dẫn harness.db")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Tạo bảng token_ledger")

    a = sub.add_parser("append", help="Gộp phiên mới thành một dòng sổ cái")
    a.add_argument("--wave", help="Mã đợt xử lý")
    a.add_argument("--batch", help="Mã lô")
    a.add_argument("--agent", default="article-processor", help="Mã tác nhân")
    a.add_argument("--items", type=int, default=0, help="Số bài đã xử lý trong đợt")
    a.add_argument("--since", type=float, help="Mốc epoch bắt đầu tính")
    a.add_argument("--window-min", type=int, default=30,
                   help="Nếu không có --since thì lấy ngược lại bấy nhiêu phút")
    a.add_argument("--cwd-filter", default="news-scape", help="Lọc phiên theo thư mục làm việc")
    a.add_argument("--est-miss", type=int, help="Dự toán token miss để đo sai số")
    a.add_argument("--est-out", type=int, help="Dự toán token out để đo sai số")
    a.add_argument("--peak", type=int, choices=[0, 1], help="Ép khung giá, bỏ trống thì tự suy")
    a.add_argument("--no-reasoning", action="store_true",
                   help="Bỏ qua việc giải nén JSONL để lấy reasoning")
    a.add_argument("--worker-calls", type=int,
                   help="Số lượt gọi worker của đợt. Bỏ trống thì đọc từ mô tả đợt, "
                        "không có mô tả thì suy thô từ số phiên")
    a.add_argument("--prefix-tokens", type=int,
                   help="Kích thước tiền tố tĩnh dùng để đối chiếu cache. Bỏ trống "
                        "thì lấy từ tệp mô tả prefix")
    a.add_argument("--note", help="Ghi chú tự do")

    r = sub.add_parser("report", help="In báo cáo sổ cái")
    r.add_argument("--wave", help="Lọc theo đợt")
    r.add_argument("--date", help="Lọc theo ngày YYYY-MM-DD")
    r.add_argument("--limit", type=int, default=30, help="Số dòng tối đa")

    v = sub.add_parser("verify", help="Đối soát sáu luật kế toán")
    v.add_argument("--cwd-filter", default="news-scape", help="Lọc phiên theo thư mục làm việc")

    args = ap.parse_args(argv)
    if args.cmd == "append" and args.peak is not None:
        args.peak = bool(args.peak)
    return {"init": cmd_init, "append": cmd_append,
            "report": cmd_report, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
