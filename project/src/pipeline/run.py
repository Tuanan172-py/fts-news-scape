"""
Pipeline orchestration — Bronze meta.json → Silver → version → work-package → catalog.

OFFLINE, re-derivable từ WORM Bronze. 1 entrypoint `process_meta` dùng bởi scripts
(build_silver, enqueue_pending, rederive_from_bronze, validate_e2e). Non-fatal per bài.
Xem phase-01/02/03/06.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.handoff.catalog import Catalog
from src.handoff.contract_validator import validate as schema_validate
from src.handoff.work_package import WorkPackageBuilder, write_package
from src.pipeline.change_detect import classify, fingerprint
from src.pipeline.silver_builder import SilverBuilder, write_silver

SCRAPER_VERSION = "capture-1.0"


def _prev_fp(v: dict | None) -> dict | None:
    if v is None:
        return None
    return {
        "content_sha256": v.get("content_sha256"),
        "simhash64": v.get("simhash64") or "0",
        "dom_path_sig": v.get("dom_path_sig") or "",
        "selector_ok": not bool(v.get("selector_drift")),
    }


def process_meta(store, meta_path: str, *, silver_dir: str = "data/silver",
                 package_dir: str = "data/work_packages",
                 t_content: int = 6, t_template: int = 12,
                 do_enqueue: bool = True) -> dict:
    """Xử lý 1 Bronze artifact → silver+version+package(+enqueue). Trả summary dict."""
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    raw_path = meta.get("html_path", "")
    if not raw_path or not Path(raw_path).exists():
        return {"article_id": meta.get("url_title_hash"), "ok": False,
                "reason": "raw_missing"}
    raw_bytes = Path(raw_path).read_bytes()

    # 1) Silver (+ hard-gate silver-v1: bug #3 — silver hỏng/cleaned rỗng → held)
    silver = SilverBuilder().build(meta, raw_bytes)
    silver_path = write_silver(silver, base_dir=silver_dir)
    silver_ok, silver_errs = schema_validate(silver, "silver-v1")
    if not silver_ok:
        logger.warning("[pipeline] silver invalid {} → held: {}", silver["article_id"],
                       silver_errs[:2])

    # 2) Change-detection version
    cur_fp = fingerprint(silver["cleaned_text"], silver["structure"],
                         content_sha256=meta.get("content_sha256", ""),
                         capture_status=meta.get("capture_status", "ok"),
                         missing=meta.get("missing", []))
    hash_ = silver["article_id"]
    prev = store.last_version(hash_)
    state, recommendation = classify(_prev_fp(prev), cur_fp,
                                     t_content=t_content, t_template=t_template)
    ham = None
    if prev:
        from src.pipeline.change_detect import hamming64
        ham = hamming64(int(prev.get("simhash64", "0") or "0", 16),
                        int(cur_fp["simhash64"], 16))
    version_id = store.insert_version({
        "url_title_hash": hash_, "source_domain": silver["domain"],
        "captured_at": meta.get("fetch_ts", ""),
        "content_sha256": cur_fp["content_sha256"], "simhash64": cur_fp["simhash64"],
        "dom_path_sig": cur_fp["dom_path_sig"], "capture_status": cur_fp["capture_status"],
        "prev_version_id": prev["id"] if prev else None,
        "hamming_content": ham,
        "dom_changed": int(bool(prev) and prev.get("dom_path_sig") != cur_fp["dom_path_sig"]),
        "selector_drift": int(not cur_fp["selector_ok"]),
        "state": state, "recommendation": recommendation,
    })

    # 3) Work-package
    article = store.get_by_hash(hash_)
    published_at = article.published_at if article else None
    package = WorkPackageBuilder().build(silver, meta, state,
                                         published_at=published_at,
                                         scraper_version=SCRAPER_VERSION)
    package_path = write_package(package, base_dir=package_dir)

    # 4) Validate (hard gate) + enqueue — held nếu silver HOẶC package không hợp lệ
    ok, errors = schema_validate(package, "work-package-v1")
    held = (not ok) or (not silver_ok)
    enq_status = None
    if do_enqueue:
        cat = Catalog(store)
        if held:
            logger.warning("[pipeline] {} → held (silver_ok={} pkg_ok={}): {}",
                           hash_, silver_ok, ok, (errors or silver_errs)[:2])
        enq_status = cat.enqueue(hash_, meta.get("content_sha256", ""),
                                 silver["domain"], package_path, state,
                                 force_held=held)

    return {"article_id": hash_, "ok": ok, "silver_ok": silver_ok, "state": state,
            "recommendation": recommendation, "version_id": version_id,
            "silver_path": silver_path, "package_path": package_path,
            "enqueue_status": enq_status, "errors": errors + silver_errs}
