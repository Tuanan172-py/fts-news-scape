"""Backfill missing trace records in harness.db for commits that already passed validation."""
import os
import re
import sys
import json
import sqlite3
import subprocess
from pathlib import Path

# Force UTF-8 stdio
sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = os.environ.get("NEWS_SCAPE_HARNESS_DB", str(REPO_ROOT / "harness.db"))


def get_commits_range(start_commit: str = "6b1c34c", end_commit: str = "HEAD") -> list[dict]:
    """List the commits in the given range, oldest first.

    Args:
        start_commit: Exclusive start of the range.
        end_commit: Inclusive end of the range.

    Returns:
        One dict per commit with `commit`, `date` and `subject`; empty if git fails.
    """
    cmd = ["git", "log", f"{start_commit}..{end_commit}", "--format=%H|%ad|%s", "--date=iso", "--reverse"]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print(f"Error fetching git log: {res.stderr}", file=sys.stderr)
        return []

    commits = []
    for line in (res.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "commit": parts[0],
                "date": parts[1],
                "subject": parts[2],
            })
    return commits


def backfill(apply: bool = False) -> None:
    """Report commits that have no trace and optionally insert the missing traces.

    Args:
        apply: Insert the missing trace rows when True; only report when False.
    """
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Commits that already have a trace.
    existing_commits = {
        row["git_commit"] for row in conn.execute("SELECT git_commit FROM trace WHERE git_commit IS NOT NULL").fetchall()
    }

    candidates = get_commits_range("6b1c34c", "HEAD")
    missing = [c for c in candidates if c["commit"] not in existing_commits]

    print(f"Tìm thấy {len(candidates)} commit từ 6b1c34c đến HEAD.")
    print(f"Đã có trace: {len(candidates) - len(missing)} commit.")
    print(f"Còn thiếu trace: {len(missing)} commit.")

    if not missing:
        print("Tất cả commit đã có trace trong harness.db. Không cần bù đắp.")
        conn.close()
        return

    story_re = re.compile(r"\((US-[A-Z0-9]+)\)")

    for c in missing:
        m = story_re.search(c["subject"])
        story_id = m.group(1) if m else "US-038"
        print(f"  [MISSING] {c['commit'][:7]} | {c['date'][:10]} | {story_id} | {c['subject']}")

        if apply:
            actions_json = json.dumps(["git_commit", "historical_backfill"], ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO trace (story_id, intake_id, task_summary, actions_taken, files_read,
                                  files_changed, outcome, score_context, score_trace, friction,
                                  error_msg, git_commit, git_branch, created_at)
                VALUES (?, NULL, ?, ?, '[]', '[]', 'completed', 1.0, 1.0, '', '', ?, 'dev/us038', ?)
                """,
                (story_id, c["subject"], actions_json, c["commit"], c["date"])
            )

    if apply:
        conn.commit()
        print(f"\n[DONE] Đã bù đắp thành công {len(missing)} trace vào {DB_PATH}.")
    else:
        print("\nChạy với cờ --apply để thực thi bù đắp vào CSDL.")

    conn.close()


if __name__ == "__main__":
    apply_flag = "--apply" in sys.argv
    backfill(apply=apply_flag)
