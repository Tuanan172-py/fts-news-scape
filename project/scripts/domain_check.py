"""
Domain Check CLI — kiểm tra domain health và tạo báo cáo.

Usage:
    python scripts/domain_check.py                  # validate tất cả domain
    python scripts/domain_check.py cafef            # validate 1 domain
    python scripts/domain_check.py --report         # tạo daily report
    python scripts/domain_check.py cafef --raw-check  # check raw response
    python scripts/domain_check.py --list           # liệt kê domain có schema

Quy trình:
    1. Đọc articles từ DB cho domain được chọn
    2. Validate field-level health so với schema.yaml
    3. Detect anomaly vs baseline 7 ngày
    4. In kết quả ra console
    5. (--report) Ghi báo cáo markdown vào data/reports/daily/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _build_http_client():
    from src.crawler.http_client import HTTPClient

    return HTTPClient(rate_limit_delay=0.5, max_retries=1)


def _build_dedup():
    from src.core.config import load_settings
    from src.db.dedup import DedupCache
    from src.db.store import ArticleStore

    settings = load_settings()
    store = ArticleStore(settings["database"]["path"])
    return DedupCache(store)


def cmd_list():
    """Liệt kê domain có schema.yaml."""
    domains_dir = Path(__file__).resolve().parent.parent / "domains"
    for d in sorted(domains_dir.iterdir()):
        if d.is_dir() and (d / "schema.yaml").exists():
            print(f"  {d.name}")


def cmd_raw_check(domain: str):
    """Kiểm tra raw response từ upstream."""
    from src.core.config import load_domain_config
    from src.scrapers import REGISTRY

    print(f"RAW CHECK: {domain}")
    print("-" * 50)

    try:
        cfg = load_domain_config(domain)
    except Exception as e:
        print(f"  CONFIG ERROR: {e}")
        return 1

    print(f"  Method: {cfg.get('method')}")
    print(f"  Enabled: {cfg.get('enabled')}")

    http = _build_http_client()
    dedup = _build_dedup()

    from src.orchestrator import build_scraper

    try:
        scraper = build_scraper(cfg, http, dedup)
    except Exception as e:
        print(f"  BUILD ERROR: {e}")
        return 1

    print(f"  Scraper: {type(scraper).__name__}")

    try:
        raw_items = scraper.fetch_list()
    except Exception as e:
        print(f"  FETCH ERROR: {e}")
        return 1

    if not raw_items:
        print("  EMPTY — no items from fetch_list()")
        return 1

    print(f"  Fetched: {len(raw_items)} items")

    # Show first item structure
    first = raw_items[0]
    print(f"\n  First item fields ({len(first)} fields):")
    for k, v in first.items():
        val_str = str(v)[:80]
        print(f"    {k:20s} = {val_str}")

    # Compare against schema
    schema_path = (
        Path(__file__).resolve().parent.parent / "domains" / domain / "schema.yaml"
    )
    if schema_path.exists():
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        expected = {f["name"] for f in schema.get("raw_response", {}).get("fields", [])}
        actual = set(first.keys())

        missing = expected - actual
        extra = actual - expected

        print(f"\n  Schema comparison:")
        print(f"    Expected: {sorted(expected)}")
        print(
            f"    Missing (expected but not in response): {sorted(missing) if missing else 'none'}"
        )
        print(
            f"    Extra (in response but not in schema):  {sorted(extra) if extra else 'none'}"
        )

    print("  OK")
    return 0


def cmd_validate(domain: str | None = None, store=None):
    """Validate articles trong DB so với schema."""
    from src.monitor.domain_validator import DomainValidator

    domains_dir = Path(__file__).resolve().parent.parent / "domains"
    domains = (
        [domain]
        if domain
        else [
            d.name
            for d in sorted(domains_dir.iterdir())
            if d.is_dir() and (d / "schema.yaml").exists()
        ]
    )

    validator = DomainValidator(store)

    exit_code = 0
    for dom in domains:
        source_domain = f"{dom}.vn" if "." not in dom else dom

        articles = []
        if store:
            try:
                conn = store._connect()
                rows = conn.execute(
                    "SELECT * FROM articles WHERE source_domain = ? "
                    "ORDER BY fetched_at DESC LIMIT 200",
                    (source_domain,),
                ).fetchall()
                from src.core.models import Article

                articles = [Article.from_row(r) for r in rows]
                conn.close()
            except Exception as e:
                print(f"[{dom}] DB ERROR: {e}")
                exit_code = 1
                continue

        print(f"[{dom}] {len(articles)} articles loaded")

        report = validator.validate_articles(dom, articles)
        print(f"  Fields: {len(report.fields)} validated")

        for field_name, stats in report.fields.items():
            status_char = {"ok": ".", "warn": "!", "fail": "X"}.get(stats.status, "?")
            print(
                f"  [{status_char}] {field_name:20s} fill={stats.fill_rate:.0%} "
                f"avg_len={stats.avg_length:.0f}"
            )

        if report.has_anomalies:
            print(f"  ANOMALIES ({len(report.anomalies)}):")
            for a in report.anomalies[:10]:
                sev = a.severity.upper()
                print(f"    [{sev}] {a.field}: {a.issue}")
            if report.has_critical:
                exit_code = 1
        else:
            print(f"  ALL OK")

        # Count anomaly
        alert_thresholds = validator.load_schema(dom).get("alert_thresholds", {})
        count_anomalies = validator.detect_count_anomaly(
            dom, len(articles), alert_thresholds
        )
        if count_anomalies:
            print(f"  COUNT ANOMALY:")
            for a in count_anomalies:
                print(f"    [{a.severity.upper()}] {a.issue}")

        print()

    return exit_code


def cmd_report(domains: list[str] | None = None):
    """Generate daily report."""
    from src.core.config import load_settings
    from src.db.store import ArticleStore
    from src.monitor.domain_reporter import DomainReporter

    settings = load_settings()
    store = ArticleStore(settings["database"]["path"])
    reporter = DomainReporter(store)

    if domains:
        paths = [reporter.generate_report(d) for d in domains]
    else:
        paths = reporter.generate_all_reports()

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"Reports generated ({today}):")
    for p in paths:
        print(f"  {p}")


def main():
    parser = argparse.ArgumentParser(
        description="Domain Check — validate domain health"
    )
    parser.add_argument(
        "domain",
        nargs="?",
        default=None,
        help="Domain to check (e.g., cafef, vietstock)",
    )
    parser.add_argument("--list", action="store_true", help="List domains with schema")
    parser.add_argument("--report", action="store_true", help="Generate daily report")
    parser.add_argument(
        "--raw-check",
        action="store_true",
        help="Check raw response from upstream (needs network)",
    )
    args = parser.parse_args()

    if args.list:
        cmd_list()
        return 0

    if args.raw_check and args.domain:
        return cmd_raw_check(args.domain)

    if args.report:
        domains = [args.domain] if args.domain else None
        cmd_report(domains)
        return 0

    from src.core.config import load_settings
    from src.db.store import ArticleStore

    settings = load_settings()
    store = ArticleStore(settings["database"]["path"])

    return cmd_validate(args.domain, store)


if __name__ == "__main__":
    sys.exit(main())
