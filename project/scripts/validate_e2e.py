"""
validate_e2e — smoke test toàn chuỗi OFFLINE (no network, no LLM). Phase-06 F3.

Bronze(synthetic) → Silver → version → work-package → schema-valid → catalog enqueue,
rồi validate agent-output-sample vs agent-output-v1 → chứng minh hợp đồng round-trip.
Exit 0 nếu PASS.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.models import Article
from src.db.store import ArticleStore
from src.handoff.catalog import Catalog
from src.handoff.contract_validator import validate as schema_validate
from src.pipeline.run import process_meta

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"

_HTML = (
    "<html><head><meta property='article:published_time' content='2026-08-13T10:00:00+07:00'/>"
    "</head><body><div id='mainContent'><h1>Tiêu đề kiểm thử</h1>"
    + "<p>Nội dung bài viết đủ dài để trafilatura bóc tách nội dung chính. </p>" * 20
    + "<figure><img data-src='https://cdn.example.vn/a.jpg' alt='minh hoạ'/>"
      "<figcaption>Ảnh minh hoạ</figcaption></figure>"
    "</div></body></html>"
)


def _make_bronze(tmp: Path) -> str:
    body = _HTML.encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    hash_ = "e2e" + sha[:61]
    d = tmp / "data" / "raw_html" / "example.vn" / "20260813"
    d.mkdir(parents=True, exist_ok=True)
    html_path = d / f"{hash_}.html"
    html_path.write_bytes(body)
    meta = {
        "source_url": "https://example.vn/tin/kiem-thu.html",
        "url_title_hash": hash_, "fetch_ts": "2026-08-13T10:00:05+07:00",
        "render_method": "requests", "html_path": str(html_path),
        "http_status": 200, "content_sha256": sha,
        "content_length_bytes": len(body), "encoding": "utf-8",
        "response_headers": {"content-type": "text/html"},
        "images": [{"outer_tag": "<img>", "resolved_url": "https://cdn.example.vn/a.jpg",
                    "alt": "minh hoạ", "title": "", "caption": "Ảnh minh hoạ"}],
        "capture_status": "ok", "missing": [], "error": None,
    }
    (d / f"{hash_}.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return str(d / f"{hash_}.meta.json"), hash_


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    tmp = Path(tempfile.mkdtemp(prefix="e2e_"))
    meta_path, hash_ = _make_bronze(tmp)
    store = ArticleStore(db_path=str(tmp / "e2e.db"))
    store.insert(Article(url="https://example.vn/tin/kiem-thu.html", title="Tiêu đề kiểm thử",
                         source_domain="example.vn", published_at="2026-08-13T10:00:00+07:00"))
    # ép url_title_hash khớp Bronze bằng cách insert version trực tiếp không cần; process_meta
    # dùng get_by_hash(hash_) → có thể None (title khác), published_at fallback None → OK.

    res = process_meta(store, meta_path,
                       silver_dir=str(tmp / "data/silver"),
                       package_dir=str(tmp / "data/work_packages"))
    checks.append(("silver built", Path(res["silver_path"]).exists(), res["silver_path"]))
    checks.append(("version state = NEW", res["state"] == "NEW", res["state"]))
    checks.append(("package schema-valid", res["ok"], str(res["errors"])[:80]))
    checks.append(("enqueued pending", res["enqueue_status"] == "pending", str(res["enqueue_status"])))

    # catalog claim round-trip
    cat = Catalog(store)
    claimed = cat.claim("e2e-worker")
    checks.append(("catalog claim works", claimed is not None and claimed["article_id"] == hash_,
                   str(claimed and claimed["status"])))
    if claimed:
        cat.mark_done(claimed["id"])
        checks.append(("mark_done → done", cat.counts().get("done", 0) == 1, str(cat.counts())))

    # agent-output sample validates
    sample = json.loads((SCHEMAS / "samples" / "agent-output-sample.json").read_text(encoding="utf-8"))
    ok_out, errs_out = schema_validate(sample, "agent-output-v1")
    checks.append(("agent-output sample valid", ok_out, str(errs_out)[:80]))

    print("\n=== E2E CHAIN VALIDATION ===")
    all_ok = True
    for name, passed, detail in checks:
        all_ok &= passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}"
              + (f"  ({detail})" if not passed else ""))
    print(f"\nRESULT: {'PASS ✅' if all_ok else 'FAIL ❌'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
