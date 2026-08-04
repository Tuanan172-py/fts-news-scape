"""
Domain Reporter — sinh báo cáo hằng ngày dạng Markdown.

Đọc dữ liệu từ DB + chạy domain_validator để tạo báo cáo
field-level health cho mỗi domain.

Usage:
    from src.monitor.domain_reporter import DomainReporter
    r = DomainReporter(store)
    r.generate_report("cafef")
"""

from __future__ import annotations

import io
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from loguru import logger

from src.core.models import VN_TZ

DOMAINS_DIR = Path(__file__).resolve().parents[2] / "domains"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports" / "daily"


class DomainReporter:
    """Sinh báo cáo markdown hằng ngày cho 1 domain."""

    def __init__(self, store=None):
        self.store = store

    def generate_report(self, domain: str, date_override: str = "") -> Path:
        """Tạo daily report cho domain, trả về path file đã tạo."""
        today = date_override or datetime.now(VN_TZ).strftime("%Y-%m-%d")
        schema = self._load_schema(domain)

        buf = io.StringIO()
        buf.write(f"# Domain Report — {domain} ({today})\n\n")

        display_name = schema.get("domain", domain) if schema else domain
        buf.write(f"## {display_name}\n\n")

        # Article stats
        stats = self._get_daily_stats(domain, today)
        buf.write(f"- **Articles today**: {stats['total_today']} new\n")
        buf.write(f"- **Articles in DB**: {stats['total_db']}\n")
        buf.write(
            f"- **Sources**: {', '.join(stats['sources']) if stats['sources'] else 'N/A'}\n\n"
        )

        # Field health table
        field_health = self._get_field_health(domain)
        if field_health:
            buf.write("### Field Health\n\n")
            buf.write("| Field | Fill Rate | Avg Length | Status |\n")
            buf.write("|------|-----------|-----------|--------|\n")
            for fh in field_health:
                status_icon = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "n/a": "N/A"}
                icon = status_icon.get(fh.get("status", "n/a"), "N/A")
                buf.write(
                    f"| {fh['field']} | {fh['fill_rate']:.0%} "
                    f"| {fh.get('avg_len', '—')} | **{icon}** |\n"
                )
            buf.write("\n")

        # Watch points
        watch_points = schema.get("watch_points", []) if schema else []
        if watch_points:
            buf.write("### Watch Points\n\n")
            for wp in watch_points:
                severity = wp.get("severity", "low").upper()
                buf.write(f"- **[{severity}]** `{wp['id']}` — {wp['description']}\n")
            buf.write("\n")

        # Recent anomalies
        anomalies = self._get_recent_anomalies(domain)
        if anomalies:
            buf.write("### Recent Anomalies\n\n")
            for a in anomalies:
                buf.write(
                    f"- `{a['field']}`: {a['issue']} ({a.get('severity', 'n/a')})\n"
                )
            buf.write("\n")
        else:
            buf.write("### Recent Anomalies\n\n*None*\n\n")

        # Summary
        buf.write("---\n")
        critical_count = sum(1 for a in anomalies if a.get("severity") == "critical")
        warn_count = sum(1 for a in anomalies if a.get("severity") == "warn")
        failed_fields = [fh for fh in field_health if fh.get("status") == "fail"]

        if critical_count == 0 and warn_count == 0 and not failed_fields:
            buf.write("**Overall: ALL OK**\n")
        else:
            buf.write(
                f"**Overall: {critical_count} critical, {warn_count} warnings, "
                f"{len(failed_fields)} failed fields**\n"
            )

        # Write to file
        report_path = REPORTS_DIR / f"{domain}-{today}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(buf.getvalue(), encoding="utf-8")

        logger.info("Report written: {}", report_path)
        return report_path

    def _load_schema(self, domain: str) -> dict | None:
        path = DOMAINS_DIR / domain / "schema.yaml"
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def _get_daily_stats(self, domain: str, date_str: str) -> dict:
        """Get article stats for today from DB."""
        if not self.store:
            return {"total_today": "N/A", "total_db": "N/A", "sources": []}

        source_domain = f"{domain}.vn" if "." not in domain else domain
        today_start = f"{date_str}T00:00:00+07:00"
        today_end = f"{date_str}T23:59:59+07:00"

        try:
            conn = self.store._connect()

            # Today's new
            total_today = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE source_domain = ? "
                "AND fetched_at >= ? AND fetched_at <= ?",
                (source_domain, today_start, today_end),
            ).fetchone()[0]

            # Total in DB
            total_db = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE source_domain = ?",
                (source_domain,),
            ).fetchone()[0]

            # Distinct sources
            sources = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT source_domain FROM articles WHERE source_domain = ?",
                    (source_domain,),
                ).fetchall()
            ]

            conn.close()
            return {
                "total_today": total_today,
                "total_db": total_db,
                "sources": sources,
            }
        except Exception as e:
            logger.warning("Stats query failed for {}: {}", domain, e)
            return {"total_today": "ERR", "total_db": "ERR", "sources": []}

    def _get_field_health(self, domain: str) -> list[dict]:
        """Get field health stats from DB for the domain."""
        if not self.store:
            return []

        source_domain = f"{domain}.vn" if "." not in domain else domain
        schema = self._load_schema(domain)
        if not schema:
            return []

        output_fields = schema.get("output_fields", {})
        health = []

        try:
            conn = self.store._connect()
            total = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE source_domain = ?",
                (source_domain,),
            ).fetchone()[0]

            if total == 0:
                conn.close()
                return [{"field": "(no data)", "fill_rate": 0.0, "status": "n/a"}]

            for field_name, field_spec in output_fields.items():
                if "." in field_name:
                    # Nested field (metadata.x) — check via metadata_json
                    col = "metadata_json"
                    parts = field_name.split(".")
                    presence = self._check_nested_presence(
                        conn, col, parts, source_domain, total
                    )
                else:
                    col = field_name
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM articles WHERE source_domain = ? "
                        f"AND {col} IS NOT NULL AND {col} != ''",
                        (source_domain,),
                    ).fetchone()
                    presence = row[0] if row else 0

                pattern = field_spec.get("pattern")
                pattern_matches = None
                if (
                    pattern
                    and presence > 0
                    and field_name not in ("content_html", "metadata")
                ):
                    try:
                        pm = conn.execute(
                            f"SELECT COUNT(*) FROM articles WHERE source_domain = ? "
                            f"AND {col} IS NOT NULL AND {col} != ''",
                            (source_domain,),
                        ).fetchone()
                    except Exception:
                        pm = None

                avg_len = "—"
                try:
                    if col not in ("metadata_json",):
                        al = conn.execute(
                            f"SELECT AVG(LENGTH({col})) FROM articles WHERE source_domain = ? "
                            f"AND {col} IS NOT NULL AND {col} != ''",
                            (source_domain,),
                        ).fetchone()
                        if al and al[0]:
                            avg_len = f"{int(al[0])}"

                except Exception:
                    avg_len = "—"

                fill_rate = presence / total if total > 0 else 0
                threshold = field_spec.get("health_threshold", 1.0)

                expected_empty = field_spec.get("expected_empty", False)
                if expected_empty:
                    status = "ok" if fill_rate <= 0.1 else "warn"
                elif fill_rate >= threshold:
                    status = "ok"
                elif fill_rate >= threshold - 0.2:
                    status = "warn"
                else:
                    status = "fail"

                health.append(
                    {
                        "field": field_name,
                        "fill_rate": fill_rate,
                        "avg_len": avg_len,
                        "threshold": threshold,
                        "status": status,
                    }
                )

            conn.close()
        except Exception as e:
            logger.warning("Field health query failed for {}: {}", domain, e)
            return [{"field": "(error)", "fill_rate": 0.0, "status": "n/a"}]

        return health

    def _check_nested_presence(
        self, conn, col: str, parts: list[str], source_domain: str, total: int
    ) -> int:
        """Check if metadata JSON contains a nested key."""
        try:
            key = parts[-1]
            rows = conn.execute(
                "SELECT metadata_json FROM articles WHERE source_domain = ? "
                "AND metadata_json IS NOT NULL AND metadata_json != '' LIMIT 1000",
                (source_domain,),
            ).fetchall()
            count = 0
            import json

            for (mj,) in rows:
                try:
                    obj = json.loads(mj)
                    if key in obj:
                        count += 1
                except json.JSONDecodeError:
                    pass
            return count
        except Exception:
            return 0

    def _get_recent_anomalies(self, domain: str) -> list[dict]:
        """Read recent anomalies from log file (if any)."""
        return []  # Placeholder — anomalies are logged via loguru, parsed on demand

    def generate_all_reports(self, domains: list[str] | None = None) -> list[Path]:
        """Generate reports for all (or specified) domains."""
        if domains is None:
            from src.core.config import list_domains as _list

            domains = _list()

        paths = []
        for d in domains:
            try:
                p = self.generate_report(d)
                paths.append(p)
            except Exception as e:
                logger.error("Failed to generate report for {}: {}", d, e)

        return paths
