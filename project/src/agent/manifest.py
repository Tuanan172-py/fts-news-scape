"""Build, load and print the batch_manifest.json summary of agent task batches."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.models import VN_TZ, now_vn_iso
from src.core.staging import safe_json_dump


def format_short_time(iso_str: str) -> str:
    """Format an ISO timestamp as the short form 'DD/MM HH:MM'.

    Args:
        iso_str: ISO 8601 timestamp string.

    Returns:
        Short timestamp for table display.
    """
    if not iso_str:
        return "--/-- --:--"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return iso_str[:16].replace("T", " ")


def extract_title(d: dict[str, Any]) -> str:
    """Extract the article title from a task object with a multi-level fallback.

    Args:
        d: Task packet or article info dict.

    Returns:
        Article title string.
    """
    if d.get("title"):
        return str(d["title"]).strip()
    inp = d.get("input") or {}
    if inp.get("title"):
        return str(inp["title"]).strip()
    headings = inp.get("structure", {}).get("headings", []) + d.get("structure", {}).get("headings", [])
    for h in headings:
        if h.get("level") == 1 and h.get("text"):
            return str(h["text"]).strip()
    ct = inp.get("cleaned_text") or d.get("cleaned_text") or ""
    if ct:
        lines = [line.strip() for line in ct.split("\n") if line.strip()]
        if lines:
            return lines[0]
    return ""


def extract_time(d: dict[str, Any]) -> str:
    """Extract the article timestamp from the candidate time fields.

    Args:
        d: Task data dict.

    Returns:
        Article timestamp string.
    """
    inp = d.get("input") or {}
    return (
        d.get("enqueued_at")
        or d.get("time")
        or inp.get("published_at")
        or inp.get("fetch_ts")
        or inp.get("captured_at")
        or ""
    )


def create_batch_manifest(
    tasks: list[dict[str, Any]],
    batch_dir: str | Path,
    *,
    batch_type: str = "gold",
    order: str = "desc",
) -> dict[str, Any]:
    """Create the batch_manifest.json file in the batch directory.

    Args:
        tasks: Task packets to record in the batch.
        batch_dir: Directory that holds the task files of the batch.
        batch_type: Batch type ('gold' or 'l1').
        order: Task ordering ('asc' or 'desc').

    Returns:
        Manifest dict that was saved.
    """
    batch_dir = Path(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(VN_TZ)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    batch_id = f"BATCH_{batch_type.upper()}_{timestamp_str}"

    articles_summary: list[dict[str, Any]] = []
    for idx, t in enumerate(tasks, start=1):
        inp = t.get("input") or {}
        article_id = t.get("article_id") or inp.get("article_id", "")
        title = extract_title(t)
        domain = t.get("domain") or inp.get("domain", "")
        ts = extract_time(t)

        articles_summary.append({
            "seq": idx,
            "article_id": article_id,
            "title": title,
            "domain": domain,
            "time": ts,
            "file": f"{article_id}.task.json",
        })

    manifest = {
        "batch_id": batch_id,
        "created_at": now_vn_iso(),
        "batch_type": batch_type,
        "batch_size": len(tasks),
        "order": order,
        "articles": articles_summary,
    }

    target_path = batch_dir / "batch_manifest.json"
    safe_json_dump(manifest, str(target_path), indent=2)
    return manifest


def print_batch_summary_table(manifest: dict[str, Any], max_rows: int = 25) -> None:
    """Print a summary table of the batch articles to the console.

    Args:
        manifest: Batch manifest data.
        max_rows: Maximum number of article rows printed.
    """
    batch_id = manifest.get("batch_id", "UNKNOWN")
    batch_size = manifest.get("batch_size", 0)
    order = manifest.get("order", "desc")
    batch_type = manifest.get("batch_type", "gold").upper()
    articles = manifest.get("articles", [])

    if not articles:
        return

    print("=" * 88)
    print(f"📦 [{batch_type} BATCH] {batch_id} ({batch_size} tin moi nhat, order={order})")
    print()
    print(f" {'STT':^3} | {'Nguon':<8} | {'Thoi gian':^11} | {'Tieu de'}")
    print("-" * 5 + "+" + "-" * 10 + "+" + "-" * 13 + "+" + "-" * 57)

    for item in articles[:max_rows]:
        seq = str(item.get("seq", "")).rjust(3)
        domain = (item.get("domain") or "")[:8].ljust(8)
        ts = format_short_time(item.get("time")).center(11)
        title = item.get("title") or ""
        title = title if len(title) <= 55 else title[:52] + "..."
        print(f" {seq} | {domain} | {ts} | {title}")

    if len(articles) > max_rows:
        print(f" ... va con {len(articles) - max_rows} bai viet nua trong batch_manifest.json")

    print("=" * 88)


def load_batch_manifest(batch_dir: str | Path) -> dict[str, Any] | None:
    """Load batch_manifest.json from the given directory if it exists.

    Args:
        batch_dir: Directory that holds batch_manifest.json.

    Returns:
        Manifest dict, or None if the file is missing or unreadable.
    """
    target = Path(batch_dir) / "batch_manifest.json"
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None
