"""Sinh tệp bàn giao trạng thái giữa hai phiên DSH với chi phí 0 token.

Toàn bộ trạng thái của pipeline đã nằm ở SQLite và ở các tệp packet trên đĩa, nên
phiên điều phối không giữ thứ gì mà cơ sở dữ liệu không có. Nhờ vậy việc bàn giao
không cần nhờ mô hình tóm tắt: script đọc thẳng cơ sở dữ liệu rồi viết ra tệp.

Đây là thứ biến việc mở phiên mới thành thao tác bình thường và rẻ, thay vì một
phương án chữa cháy khi ngữ cảnh đã phình. Mất phiên giữa chừng chỉ mất đúng lô
đang chạy, và packet của lô đó vẫn còn trên đĩa để chạy lại.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.article_pack import ANALYZED_L1, load_candidates  # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.db.preflight import resolve_db_path         # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
STATE_DIR = DATA_ROOT / "state"
ARTICLE_TASK_DIR = DATA_ROOT / "agent_tasks" / "article"
ARTICLE_OUT_DIR = DATA_ROOT / "agent_outputs_article"


def get_db_connection() -> sqlite3.Connection:
    """Mở kết nối chỉ đọc tới đúng cơ sở dữ liệu mà bước nạp ghi vào.

    Returns:
        Kết nối SQLite tới `monocle.db`.
    """
    conn = sqlite3.connect(f"file:{resolve_db_path().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> int:
    """Chạy một truy vấn trả về một số và bọc lỗi thành 0.

    Args:
        cur: Con trỏ SQLite đang mở.
        sql: Câu truy vấn trả về đúng một giá trị số.
        params: Tham số truyền vào truy vấn.

    Returns:
        Giá trị số đọc được, hoặc 0 khi truy vấn lỗi hoặc rỗng.
    """
    try:
        row = cur.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def collect_state(today: str) -> dict:
    """Thu thập toàn bộ trạng thái cần cho việc bàn giao.

    Args:
        today: Ngày cần thống kê theo định dạng YYYY-MM-DD.

    Returns:
        Từ điển trạng thái gồm độ phủ, số bài chờ phân tích và packet chưa chạy.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    state = {
        "today": today,
        "articles_today": _scalar(
            cur, "SELECT count(*) FROM articles WHERE substr(published_at,1,10)=?", (today,)),
        "l1_done_today": _scalar(
            cur, "SELECT count(*) FROM l1_outputs o JOIN articles a "
                 "ON a.url_title_hash=o.article_id "
                 f"WHERE substr(a.published_at,1,10)=? AND {ANALYZED_L1}", (today,)),
        "gold_done_today": _scalar(
            cur, "SELECT count(*) FROM agent_outputs o JOIN articles a "
                 "ON a.url_title_hash=o.article_id "
                 "WHERE substr(a.published_at,1,10)=? AND o.dod_pass=1", (today,)),
    }
    # Cùng câu truy vấn với bước đóng gói, nên con số này đúng bằng số bài mà đợt kế
    # tiếp sẽ lấy.
    state["pending_today"] = len(load_candidates(conn, date=today, limit=1_000_000,
                                                 only_pending=True))
    conn.close()

    packets = sorted(glob.glob(str(ARTICLE_TASK_DIR / "*.task.json")))
    outputs = {Path(p).name.replace(".output.json", "")
               for p in glob.glob(str(ARTICLE_OUT_DIR / "*.output.json"))}
    pending_packets = [p for p in packets
                       if Path(p).name.replace(".task.json", "") not in outputs]

    state["packets_total"] = len(packets)
    state["packets_pending"] = pending_packets
    return state


def render(state: dict, wave: str | None, prefix_hash: str | None) -> str:
    """Kết xuất trạng thái thành tệp bàn giao dạng Markdown.

    Args:
        state: Từ điển trạng thái do :func:`collect_state` trả về.
        wave: Mã đợt đang dở, nếu có.
        prefix_hash: Giá trị băm của prefix đang dùng, nếu có.

    Returns:
        Nội dung Markdown của tệp bàn giao.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    covered = state["l1_done_today"]
    total = state["articles_today"]
    pct = (covered / total * 100) if total else 0.0
    pending = state["packets_pending"]

    lines = [
        f"# HANDOFF — {ts}",
        "",
        "Tệp này do `handoff.py` sinh tự động từ cơ sở dữ liệu, **0 token**.",
        "Phiên mới chỉ cần đọc tệp này rồi chạy lệnh ở mục Bước tiếp theo.",
        "",
        "## Độ phủ hôm nay",
        "",
        f"- Bài đăng trong ngày: **{total}**",
        f"- Đã xong nhận diện thực thể: **{covered}** ({pct:.1f}%)",
        f"- Đã xong phân tích nội dung: **{state['gold_done_today']}**",
        f"- Chờ phân tích: **{state['pending_today']}** bài có gói Silver",
        "",
        "## Wave đang dở",
        "",
        f"- Mã đợt: **{wave or 'không có'}**",
        f"- Packet trên đĩa: {state['packets_total']} · **chưa chạy: {len(pending)}**",
    ]
    for p in pending[:10]:
        lines.append(f"  - `{Path(p).name}`")
    if len(pending) > 10:
        lines.append(f"  - … và {len(pending) - 10} tệp nữa")

    lines += [
        "",
        "## Prefix",
        "",
        f"- Hash đang dùng: `{prefix_hash or 'chưa sinh'}`",
        "- Prefix đổi giữa chừng là mất cache. Kiểm bằng `article_run.py --check-prefix`.",
        "",
        "## Bước tiếp theo",
        "",
    ]
    if pending:
        lines.append(f"```powershell\npython scripts/article_run.py --wave {wave or 'next'} --resume\n```")
        lines.append("")
        lines.append(f"Còn {len(pending)} lô chưa chạy trong đợt này; `--resume` bỏ qua lô đã có output.")
    else:
        lines.append("```powershell\npython scripts/pipeline_radar.py status\n```")
        lines.append("")
        lines.append(f"Không còn lô dở. Radar in đúng lệnh mở đợt mới cho "
                     f"{state['pending_today']} bài đang chờ, hoặc lệnh giao hàng.")

    lines += [
        "",
        "## Nhắc",
        "",
        "- Đóng phiên cũ sau khi đọc tệp này. Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình,",
        "  vì bộ nhớ đệm nằm ở phía nhà cung cấp chứ không gắn với phiên.",
        "- Phiên mới phải dùng đúng preset `news-scape-conductor`. Sai preset là mất ranh giới",
        "  công cụ của agent con, đúng nguyên nhân gốc của vệt 845 nghìn token ngày 17/09.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh sinh tệp bàn giao.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0.
    """
    ap = argparse.ArgumentParser(description="Sinh tệp bàn giao trạng thái 0 token")
    ap.add_argument("--wave", help="Mã đợt đang dở")
    ap.add_argument("--prefix-hash", help="Hash prefix đang dùng")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="Ngày thống kê YYYY-MM-DD")
    ap.add_argument("--stdout", action="store_true", help="In ra màn hình thay vì ghi tệp")
    ap.add_argument("--json", action="store_true", help="Xuất trạng thái dạng JSON")
    args = ap.parse_args(argv)

    state = collect_state(args.date)
    if args.json:
        printable = dict(state)
        printable["packets_pending"] = [Path(p).name for p in state["packets_pending"]]
        print(json.dumps(printable, ensure_ascii=False, indent=2))
        return 0

    content = render(state, args.wave, args.prefix_hash)
    if args.stdout:
        print(content)
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / f"HANDOFF-{datetime.now():%Y%m%dT%H%M%S}.md"
    out.write_text(content, encoding="utf-8")
    latest = STATE_DIR / "HANDOFF-latest.md"
    latest.write_text(content, encoding="utf-8")
    print(f"✅ Đã ghi bàn giao: {out}")
    print(f"   Bản mới nhất  : {latest}")
    print(f"   Độ phủ hôm nay: {state['l1_done_today']}/{state['articles_today']} · "
          f"lô chưa chạy: {len(state['packets_pending'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
