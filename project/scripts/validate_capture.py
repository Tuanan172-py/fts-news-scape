"""
Audit end-to-end cơ chế RAW HTML CAPTURE (CafeF + Vietstock) — chạy LIVE.

Xây scraper thật, HTTPClient thật, fetch vài bài, lưu raw artifact vào thư mục
tạm, rồi in báo cáo kiểm chứng: capture_status, byte-exact sha256, images[],
headers, robots, missing. Không đụng DB production (dùng temp DB).

Usage:
    python scripts/validate_capture.py            # cafef + vietstock, mỗi nguồn 2 bài
    python scripts/validate_capture.py cafef 3    # chỉ cafef, 3 bài
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_domain_config
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.orchestrator import build_scraper


def _audit_source(name: str, n: int, raw_dir: str, dedup: DedupCache) -> None:
    print(f"\n{'='*70}\n  NGUỒN: {name}  (giới hạn {n} bài)\n{'='*70}")
    cfg = load_domain_config(name)
    cfg.setdefault("capture", {})["raw_dir"] = raw_dir
    cfg["detail"] = {**cfg.get("detail", {}), "max_details_per_cycle": n}
    if name == "cafef":
        cfg["watchlist"] = ["FPT"]

    http = HTTPClient(rate_limit_delay=cfg.get("rate_limit", 3.0))
    scraper = build_scraper(cfg, http, dedup)
    result = scraper.run()

    captured = [a for a in result.new if a.metadata.get("capture")]
    print(f"fetched={result.fetched}  new={len(result.new)}  "
          f"captured={len(captured)}  errors={len(result.errors)}")
    for e in result.errors[:5]:
        print(f"  ERR: {e}")

    status_count: dict[str, int] = {}
    for a in captured:
        st = a.metadata["capture"].get("capture_status", "?")
        status_count[st] = status_count.get(st, 0) + 1
    print(f"capture_status: {status_count}")

    # chi tiết 1 bài ok đầu tiên
    ok = next((a for a in captured
               if a.metadata["capture"].get("capture_status") == "ok"), None)
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
    print(f"  sha256 match   : "
          f"{cap['content_sha256'] == hashlib.sha256(disk).hexdigest()}")
    print(f"  http_status    : {cap['http_status']}")
    print(f"  headers        : {list(cap['response_headers'].keys())}")
    print(f"  images         : {len(cap['images'])} (sample: "
          f"{cap['images'][0]['resolved_url'] if cap['images'] else 'n/a'})")
    print(f"  missing        : {cap['missing']}")
    print(f"  content_html   : {len(sample.content_html)} chars (sub-region)")
    # kiểm chứng meta.json trên đĩa
    meta_path = html_path.with_suffix("").as_posix() + ".meta.json"
    mp = Path(cap['html_path'][:-len('.html')] + '.meta.json')
    print(f"  meta.json      : exists={mp.exists()}")
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
        print(f"  meta keys      : {sorted(meta.keys())}")


def main() -> int:
    args = sys.argv[1:]
    sources = ["cafef", "vietstock"]
    n = 2
    if args:
        if args[0] in ("cafef", "vietstock"):
            sources = [args[0]]
        if len(args) > 1 and args[-1].isdigit():
            n = int(args[-1])

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
