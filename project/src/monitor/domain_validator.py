"""Kiểm định chất lượng các trường dữ liệu của bài viết theo lược đồ schema.yaml.

Cung cấp lớp DomainValidator và các cấu trúc dữ liệu thống kê để theo dõi tỷ lệ
điền đầy (fill rate), độ khớp định dạng (pattern match) và phát hiện bất thường (anomaly).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.core.models import Article, VN_TZ

DOMAINS_DIR = Path(__file__).resolve().parents[2] / "domains"


@dataclass
class FieldStats:
    """Số liệu thống kê chất lượng dữ liệu của một trường sau kiểm định.

    Attributes:
        field_name: Tên trường dữ liệu.
        total: Tổng số bài viết được kiểm tra.
        present: Số lượng bài viết có trường dữ liệu này.
        missing: Số lượng bài viết thiếu trường dữ liệu.
        pattern_matches: Số lượng bài viết khớp định dạng quy chuẩn.
        pattern_fails: Số lượng bài viết không khớp định dạng.
        avg_length: Độ dài chuỗi ký tự trung bình của trường.
        status: Trạng thái đánh giá tổng quát ('ok', 'warn', 'fail').
    """

    field_name: str
    total: int = 0
    present: int = 0
    missing: int = 0
    pattern_matches: int = 0
    pattern_fails: int = 0
    avg_length: float = 0.0
    status: str = "ok"

    @property
    def fill_rate(self) -> float:
        """Tỷ lệ bài viết có điền dữ liệu trên tổng số bài."""
        return self.present / self.total if self.total > 0 else 1.0

    @property
    def pattern_rate(self) -> float:
        """Tỷ lệ dữ liệu khớp mẫu định dạng biểu thức chính quy."""
        return self.pattern_matches / self.present if self.present > 0 else 1.0


@dataclass
class Anomaly:
    """Bản ghi phát hiện dấu hiệu bất thường về chất lượng dữ liệu.

    Attributes:
        field: Tên trường dữ liệu có bất thường.
        issue: Mã định danh vấn đề phát hiện.
        current_value: Giá trị đo lường hiện tại.
        baseline_value: Giá trị chuẩn đối chiếu (nếu có).
        delta_pct: Tỷ lệ phần trăm sai lệch so với chuẩn.
        severity: Mức độ nghiêm trọng ('info', 'warn', 'critical').
    """

    field: str
    issue: str
    current_value: Any
    baseline_value: Any | None
    delta_pct: float | None
    severity: str


@dataclass
class ValidationReport:
    """Báo cáo tổng hợp kết quả kiểm định chất lượng dữ liệu của một tên miền.

    Attributes:
        domain: Tên miền của nguồn tin tức.
        timestamp: Thời điểm lập báo cáo kiểm định theo chuẩn ISO 8601.
        article_count: Tổng số bài viết được kiểm định.
        fields: Bản đồ số liệu thống kê chi tiết theo từng trường.
        anomalies: Danh sách các điểm bất thường phát hiện được.
    """

    domain: str
    timestamp: str
    article_count: int
    fields: dict[str, FieldStats] = field(default_factory=dict)
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def has_anomalies(self) -> bool:
        """Kiểm tra báo cáo có ghi nhận bất thường hay không."""
        return len(self.anomalies) > 0

    @property
    def has_critical(self) -> bool:
        """Kiểm tra báo cáo có bất thường mức độ nghiêm trọng (critical) hay không."""
        return any(a.severity == "critical" for a in self.anomalies)

    def anomalies_summary(self) -> str:
        """Tóm tắt ngắn gọn danh sách các điểm bất thường phát hiện được."""
        if not self.anomalies:
            return "none"
        return "; ".join(f"{a.field}:{a.issue}" for a in self.anomalies[:5])


class DomainValidator:
    """Bộ kiểm tra tính tuân thủ trường dữ liệu của bài viết so với cấu hình domain.

    Attributes:
        store: Đối tượng cơ sở dữ liệu để truy vấn số liệu tham chiếu lịch sử.
    """

    def __init__(self, store=None):
        self.store = store
        self._schemas: dict[str, dict] = {}

    def load_schema(self, domain: str) -> dict | None:
        """Tải cấu hình schema.yaml cho một tên miền nguồn tin tức.

        Args:
            domain: Tên định danh của tên miền nguồn (ví dụ: 'cafef').

        Returns:
            Từ điển cấu hình lược đồ, hoặc None nếu không tìm thấy tệp.
        """
        if domain in self._schemas:
            return self._schemas[domain]
        path = DOMAINS_DIR / domain / "schema.yaml"
        if not path.exists():
            logger.warning("Schema not found: {}", path)
            return None
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._schemas[domain] = schema
        return schema

    def validate_articles(
        self, domain: str, articles: list[Article]
    ) -> ValidationReport:
        """Kiểm định một tập hợp bài viết so với lược đồ định nghĩa của tên miền.

        Args:
            domain: Tên miền nguồn cần kiểm định.
            articles: Danh sách đối tượng bài viết Article.

        Returns:
            Đối tượng ValidationReport tổng hợp kết quả kiểm định.
        """
        schema = self.load_schema(domain)
        if not schema:
            return ValidationReport(
                domain=domain,
                timestamp=datetime.now(VN_TZ).isoformat(),
                article_count=len(articles),
                anomalies=[Anomaly("schema", "missing", None, None, None, "critical")],
            )

        output_fields = schema.get("output_fields", {})
        report = ValidationReport(
            domain=domain,
            timestamp=datetime.now(VN_TZ).isoformat(),
            article_count=len(articles),
        )

        if not articles:
            report.anomalies.append(
                Anomaly(
                    field="articles",
                    issue="zero_articles",
                    current_value=0,
                    baseline_value=None,
                    delta_pct=None,
                    severity="warn",
                )
            )
            return report

        for field_spec_name, field_spec in output_fields.items():
            stats = self._validate_field(articles, field_spec_name, field_spec)
            report.fields[field_spec_name] = stats

            threshold = field_spec.get("health_threshold", 1.0)
            if stats.fill_rate < threshold:
                delta = (threshold - stats.fill_rate) * 100
                severity = "critical" if delta > 30 else "warn"
                report.anomalies.append(
                    Anomaly(
                        field=field_spec_name,
                        issue=f"fill_rate {stats.fill_rate:.0%} < threshold {threshold:.0%}",
                        current_value=stats.fill_rate,
                        baseline_value=threshold,
                        delta_pct=delta,
                        severity=severity,
                    )
                )

            pattern = field_spec.get("pattern")
            if pattern and stats.pattern_fails > 0:
                report.anomalies.append(
                    Anomaly(
                        field=field_spec_name,
                        issue=f"pattern mismatch: {stats.pattern_fails}/{stats.present}",
                        current_value=stats.pattern_rate,
                        baseline_value=1.0,
                        delta_pct=(1.0 - stats.pattern_rate) * 100,
                        severity="warn",
                    )
                )

        return report

    def _validate_field(
        self, articles: list[Article], field_name: str, spec: dict
    ) -> FieldStats:
        """Validate 1 field trên batch articles."""
        stats = FieldStats(field_name=field_name, total=len(articles))
        pattern = spec.get("pattern")
        min_length = spec.get("min_length", 0)
        expected_empty = spec.get("expected_empty", False)
        total_length = 0

        for a in articles:
            value = self._get_field_value(a, field_name)
            present = value is not None and (
                not isinstance(value, str) or len(value) > 0
            )

            if expected_empty:
                # Field này kỳ vọng luôn rỗng (vd: author của CafeF)
                if not present:
                    stats.present += 1
                else:
                    stats.missing += 1
                continue

            if present:
                stats.present += 1
                if isinstance(value, str):
                    total_length += len(value)
                elif isinstance(value, list):
                    total_length += sum(len(str(x)) for x in value)

                if pattern and isinstance(value, str):
                    if re.match(pattern, value):
                        stats.pattern_matches += 1
                    else:
                        stats.pattern_fails += 1
            else:
                stats.missing += 1

        if stats.present > 0:
            stats.avg_length = total_length / stats.present

        stats.status = self._compute_status(stats, spec)
        return stats

    def _get_field_value(self, article: Article, field_name: str) -> Any:
        """Lấy field value từ Article object, hỗ trợ nested (vd: metadata.image)."""
        if "." in field_name:
            parts = field_name.split(".")
            obj = getattr(article, parts[0], None)
            for p in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(p)
                else:
                    return None
            return obj
        return getattr(article, field_name, None)

    def _compute_status(self, stats: FieldStats, spec: dict) -> str:
        threshold = spec.get("health_threshold", 1.0)
        if stats.fill_rate >= threshold:
            return "ok"
        if stats.fill_rate >= threshold - 0.2:
            return "warn"
        return "fail"

    def load_baseline(self, domain: str, days: int = 7) -> dict | None:
        """Đọc baseline field stats từ DB metrics trong N ngày qua."""
        if not self.store:
            return None

        since = datetime.now(VN_TZ) - timedelta(days=days)
        since_str = since.isoformat()

        try:
            conn = self.store._connect()
            rows = conn.execute(
                """SELECT articles_fetched, articles_new, errors, duration_ms
                   FROM scraper_metrics
                   WHERE scraper_name = ? AND ts >= ?
                   ORDER BY ts""",
                (domain, since_str),
            ).fetchall()
            conn.close()

            if not rows:
                return None

            total_new = sum(r[1] for r in rows)
            total_fetched = sum(r[0] for r in rows)
            total_errors = sum(r[2] for r in rows)

            return {
                "cycles": len(rows),
                "total_new": total_new,
                "avg_new_per_cycle": total_new / len(rows),
                "total_fetched": total_fetched,
                "total_errors": total_errors,
            }
        except Exception as e:
            logger.warning("Failed to load baseline for {}: {}", domain, e)
            return None

    def detect_count_anomaly(
        self, domain: str, current_new: int, alert_thresholds: dict
    ) -> list[Anomaly]:
        """Detect article count anomaly vs baseline."""
        baseline = self.load_baseline(domain)
        if not baseline:
            return []

        anomalies = []
        drop_pct = alert_thresholds.get("article_count_drop_pct", 50)
        avg = baseline["avg_new_per_cycle"]

        if avg > 0 and current_new < avg * (1 - drop_pct / 100):
            actual_drop = (1 - current_new / avg) * 100
            anomalies.append(
                Anomaly(
                    field="article_count",
                    issue=f"drop {actual_drop:.0f}% vs baseline avg {avg:.0f}",
                    current_value=current_new,
                    baseline_value=avg,
                    delta_pct=actual_drop,
                    severity="critical" if actual_drop > 70 else "warn",
                )
            )

        return anomalies

    def validate_raw_response(
        self, domain: str, raw_items: list[dict]
    ) -> dict[str, FieldStats]:
        """Validate raw response structure (field presence, type)."""
        schema = self.load_schema(domain)
        if not schema:
            return {}

        raw_spec = schema.get("raw_response", {})
        expected_fields = raw_spec.get("fields", [])

        stats = {}
        for field_def in expected_fields:
            name = field_def["name"]
            fs = FieldStats(field_name=f"raw.{name}", total=len(raw_items))
            for item in raw_items:
                value = item.get(name)
                if value is not None:
                    fs.present += 1
                else:
                    fs.missing += 1
            fs.status = "ok" if fs.fill_rate >= 0.9 else "warn"
            stats[name] = fs

        return stats
