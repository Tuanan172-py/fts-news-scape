"""Generate the state hand-off file between two DSH sessions at zero token cost by reading SQLite and the packet files directly."""
# All pipeline state lives in SQLite and in the packet files on disk, so the conductor
# session holds nothing the database lacks and no model summary is needed. This makes
# opening a new session a cheap routine step. Losing a session mid-run loses only the
# batch in flight, whose packet stays on disk for a rerun.
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
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.db.preflight import resolve_db_path         # noqa: E402
from src.db.connect import open_ro  # noqa: E402

force_utf8_stdio()

STATE_DIR = paths.state_dir()
ARTICLE_TASK_DIR = paths.article_packets_dir()
ARTICLE_OUT_DIR = paths.agent_outputs_dir("_article")


def get_db_connection() -> sqlite3.Connection:
    """Open a read-only connection to the database that the ingest step writes to.

    Returns:
        SQLite connection to `monocle.db`.
    """
    conn = open_ro(resolve_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> int:
    """Run a single-number query and map errors to 0.

    Args:
        cur: Open SQLite cursor.
        sql: Query that returns exactly one numeric value.
        params: Query parameters.

    Returns:
        The numeric value read, or 0 when the query fails or returns nothing.
    """
    try:
        row = cur.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def wave_date(wave: str | None) -> str | None:
    """Read the data date of a wave from its packing manifest.

    The hand-off must report the day the wave processed, not the day the command runs.
    A catch-up wave for an older day would otherwise print zero coverage even though
    its own post-check already met the threshold.

    Args:
        wave: Wave code, or None when the wave is unknown.

    Returns:
        Date as YYYY-MM-DD recorded in the manifest, or None when unreadable.
    """
    if not wave:
        return None
    for name in (f"{wave}.json", f"wave_{wave}.json"):
        path = ARTICLE_TASK_DIR / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        date = data.get("date") or data.get("wave_date")
        if date:
            return str(date)[:10]
    return None


def collect_state(today: str, wave: str | None = None) -> dict:
    """Collect all state needed for the hand-off.

    Args:
        today: Day to report on, formatted YYYY-MM-DD.
        wave: Wave code under consideration. When given, unrun packets are counted
            only within that wave; otherwise every packet on disk is counted.

    Returns:
        State dict with coverage, the number of articles awaiting analysis and unrun packets.
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
    # Same query as the packing step, so this count equals the articles the next wave will take.
    state["pending_today"] = len(load_candidates(conn, date=today, limit=1_000_000,
                                                 only_pending=True))
    conn.close()

    # Restrict to the wave when its code is known. Stray packets of other waves stay on
    # disk routinely; counting them would report unrun batches for a finished wave and
    # give the next session a wrong follow-up command.
    pattern = f"article_{wave}_*.task.json" if wave else "*.task.json"
    packets = sorted(glob.glob(str(ARTICLE_TASK_DIR / pattern)))
    outputs = {Path(p).name.replace(".output.json", "")
               for p in glob.glob(str(ARTICLE_OUT_DIR / pattern.replace(".task.json",
                                                                   ".output.json")))}
    pending_packets = [p for p in packets
                       if Path(p).name.replace(".task.json", "") not in outputs]

    state["packets_total"] = len(packets)
    state["packets_pending"] = pending_packets
    state["wave"] = wave
    return state


def render(state: dict, wave: str | None, prefix_hash: str | None) -> str:
    """Render the state as a Markdown hand-off file.

    Args:
        state: State dict returned by :func:`collect_state`.
        wave: Code of the unfinished wave, if any.
        prefix_hash: Hash of the prefix in use, if any.

    Returns:
        Markdown content of the hand-off file.
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
        f"## Độ phủ ngày {state['today']}",
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
    """Run the command line that generates the hand-off file.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv`.

    Returns:
        Exit code, always 0.
    """
    ap = argparse.ArgumentParser(description="Sinh tệp bàn giao trạng thái 0 token")
    ap.add_argument("--wave", help="Mã đợt đang dở")
    ap.add_argument("--prefix-hash", help="Hash prefix đang dùng")
    ap.add_argument("--date", help="Ngày thống kê YYYY-MM-DD")
    ap.add_argument("--stdout", action="store_true", help="In ra màn hình thay vì ghi tệp")
    ap.add_argument("--json", action="store_true", help="Xuất trạng thái dạng JSON")
    args = ap.parse_args(argv)

    args.date = args.date or wave_date(args.wave) or datetime.now().strftime("%Y-%m-%d")
    state = collect_state(args.date, args.wave)
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
    print(f"   Độ phủ ngày {state['today']}: "
          f"{state['l1_done_today']}/{state['articles_today']} · "
          f"lô chưa chạy: {len(state['packets_pending'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
