"""Audit the quality of the raw artifact (Bronze) capture and storage mechanism."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import list_domains, load_domain_config
from src.core.stdio import force_utf8_stdio
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.orchestrator import build_scraper

force_utf8_stdio()


def _audit_source(name: str, n: int, raw_dir: str, dedup: DedupCache) -> None:
    """Run one source and print the capture audit of its results.

    Args:
        name: Domain name of the source.
        n: Maximum number of detail fetches for the audit.
        raw_dir: Directory that receives the captured raw HTML.
        dedup: Deduplication cache shared across sources.
    """
    print(f"\n{'=' * 70}\n  NGUỒN: {name}  (giới hạn {n} bài)\n{'=' * 70}")
    cfg = load_domain_config(name)
    cfg.setdefault("capture", {})["raw_dir"] = raw_dir
    cfg["detail"] = {**cfg.get("detail", {}), "max_details_per_cycle": n}
    # Watchlist-driven sources (cafef, fireant) issue one request per symbol; reduce to
    # one symbol so the audit does not send 30 requests to check 2 articles.
    if cfg.get("api", {}).get("params") or cfg.get("auth"):
        cfg["watchlist"] = ["FPT"]

    http = HTTPClient(rate_limit_delay=cfg.get("rate_limit", 3.0))
    scraper = build_scraper(cfg, http, dedup)
    result = scraper.run()

    captured = [a for a in result.new if a.metadata.get("capture")]
    print(
        f"fetched={result.fetched}  new={len(result.new)}  "
        f"captured={len(captured)}  errors={len(result.errors)}"
    )
    for e in result.errors[:5]:
        print(f"  ERR: {e}")

    status_count: dict[str, int] = {}
    for a in captured:
        st = a.metadata["capture"].get("capture_status", "?")
        status_count[st] = status_count.get(st, 0) + 1
    print(f"capture_status: {status_count}")

    # details of the first article with status ok
    ok = next(
        (a for a in captured if a.metadata["capture"].get("capture_status") == "ok"),
        None,
    )
    sample = ok or (captured[0] if captured else None)
    if sample is None:
        print("  (không có bài nào được capture)")
        return
    cap = sample.metadata["capture"]
    html_path = Path(cap["html_path"])
    disk = html_path.read_bytes() if html_path.exists() else b""
    import hashlib

    print(f"\n  ── SAMPLE ──\n  url            : {sample.url}")
    print(f"  title          : {sample.title[:70]}")
    print(f"  published_at   : {sample.published_at}")
    print(f"  html_path      : {cap['html_path']}")
    print(f"  file exists    : {html_path.exists()}  ({len(disk)} bytes)")
    print(
        f"  sha256 match   : "
        f"{cap['content_sha256'] == hashlib.sha256(disk).hexdigest()}"
    )
    print(f"  http_status    : {cap['http_status']}")
    print(f"  headers        : {list(cap['response_headers'].keys())}")
    print(
        f"  images         : {len(cap['images'])} (sample: "
        f"{cap['images'][0]['resolved_url'] if cap['images'] else 'n/a'})"
    )
    print(f"  missing        : {cap['missing']}")
    print(f"  content_html   : {len(sample.content_html)} chars (sub-region)")
    # verify the meta.json on disk
    meta_path = html_path.with_suffix("").as_posix() + ".meta.json"
    mp = Path(cap["html_path"][: -len(".html")] + ".meta.json")
    print(f"  meta.json      : exists={mp.exists()}")
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
        print(f"  meta keys      : {sorted(meta.keys())}")


def main() -> int:
    """Run the capture audit for the selected or all capture-enabled sources.

    Returns:
        Exit code 0.
    """
    args = sys.argv[1:]
    n = 2
    if args and args[-1].isdigit():
        n = int(args[-1])
        args = args[:-1]
    skipped: list[str] = []
    if args:
        sources = args
    else:
        # default: every enabled domain that declares capture (no hardcoded source names)
        sources = []
        for d in list_domains():
            if (load_domain_config(d).get("capture") or {}):
                sources.append(d)
            else:
                skipped.append(d)
    print(f"Nguồn audit: {', '.join(sources)}")
    if skipped:
        # Skipping silently would give a false sense of safety: these sources RUN without
        # storing Bronze, so there is nothing to verify and nothing to recover.
        print(f"⚠️  BỎ QUA {len(skipped)} domain đang BẬT nhưng KHÔNG khai `capture:` "
              f"→ {', '.join(skipped)}")
        print("    Những nguồn này không lưu Bronze raw HTML: không audit được, và mất "
              "bài khi nguồn gỡ. Xem project/docs/dev/03-adding-a-source.md §2b.")

    tmp = tempfile.mkdtemp(prefix="capture_audit_")
    raw_dir = str(Path(tmp) / "raw_html")
    store = ArticleStore(db_path=str(Path(tmp) / "audit.db"))
    dedup = DedupCache(store, legacy_json_path="")
    print(f"Temp raw_dir: {raw_dir}")
    try:
        for s in sources:
            try:
                _audit_source(s, n, raw_dir, dedup)
            except Exception as e:  # noqa: BLE001
                print(f"  !! {s} audit failed: {type(e).__name__}: {e}")
    finally:
        dedup.close()
    print(f"\nArtifacts giữ tại: {raw_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
