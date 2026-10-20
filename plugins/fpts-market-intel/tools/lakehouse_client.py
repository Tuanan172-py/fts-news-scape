"""Động cơ DuckDB nhúng và bộ điều phối truy vấn Lakehouse cho fpts-market-intel."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]


DEFAULT_SHORTCUT_NAMES = [
    "FRA_DataIngestion - news-data",
    "news-data",
]

THEMES_FILE = Path(__file__).resolve().parents[1] / "config" / "themes.json"

# Cột tối thiểu mà các lens cần; cột thiếu trong Parquet được bù NULL để chịu được lệch schema.
REQUIRED_COLUMNS: dict[str, str] = {
    "article_id": "VARCHAR",
    "url": "VARCHAR",
    "title": "VARCHAR",
    "source_domain": "VARCHAR",
    "published_at": "VARCHAR",
    "summary": "VARCHAR",
    "key_points": "VARCHAR[]",
    "implication": "VARCHAR",
    "sentiment": "VARCHAR",
    "time_sensitivity": "VARCHAR",
    "entities": "VARCHAR[]",
    "symbols": "VARCHAR[]",
    "intent_source": "VARCHAR",
}

MACRO_KINDS = ("MACRO_THEME", "MACRO_GEO", "INSTITUTION", "ASSET_CLASS", "INDEX")
SECTOR_KINDS = ("IND_GICS1", "IND_GICS2", "IND_GICS3")
Z_SD_FLOOR = 0.5
MIN_DAY_ARTICLES_FOR_PULSE = 5

STORY_COLUMNS = """
    story_key,
    arg_min(article_id, published_at) AS article_id,
    arg_min(title, published_at) AS title,
    min(published_at) AS first_published,
    max(published_at) AS last_published,
    count(*) AS n_articles,
    count(DISTINCT source_domain) AS n_sources,
    list(DISTINCT source_domain ORDER BY source_domain) AS sources,
    arg_min(source_domain, published_at) AS first_source,
    arg_min(url, published_at) AS url,
    arg_min(summary, published_at) AS summary,
    arg_min(key_points, published_at) AS key_points,
    arg_min(implication, published_at) AS implication,
    arg_min(sentiment, published_at) AS sentiment,
    arg_min(time_sensitivity, published_at) AS time_sensitivity,
    bool_or(is_hot) AS is_hot
"""


def resolve_lakehouse_root(custom_root: str | Path | None = None) -> Path:
    """Xác định đường dẫn thư mục Lakehouse cục bộ theo giao thức Auto-Discovery 3 cấp.

    Args:
        custom_root: Đường dẫn ghi đè nếu được chỉ định trực tiếp.

    Returns:
        Đường dẫn Path tới thư mục gốc Lakehouse chứa _manifest/latest.json.

    Raises:
        FileNotFoundError: Khi không thể tự động nhận diện thư mục Lakehouse.
    """
    if custom_root:
        p = Path(custom_root).resolve()
        if (p / "_manifest" / "latest.json").exists():
            return p
        raise FileNotFoundError(f"Không tìm thấy _manifest/latest.json tại: {p}")

    env_root = os.environ.get("NEWS_DATA_ROOT") or os.environ.get("NEWS_SCAPE_PUBLISH_DIR")
    if env_root:
        p = Path(env_root).resolve()
        if (p / "_manifest" / "latest.json").exists():
            return p

    home = Path.home()
    candidate_dirs = [
        home / "OneDrive - fpts.com.vn" / "Shortcuts",
        home / "OneDrive - fpts.com.vn",
        home / "OneDrive" / "Shortcuts",
        home / "OneDrive",
        home,
    ]

    for base in candidate_dirs:
        for name in DEFAULT_SHORTCUT_NAMES:
            candidate = base / name
            if (candidate / "_manifest" / "latest.json").exists():
                return candidate.resolve()

    for entry in home.glob("OneDrive*/**/_manifest/latest.json"):
        return entry.parent.parent.resolve()

    raise FileNotFoundError(
        "Không thể tự động tìm thấy thư mục Lakehouse (FRA_DataIngestion - news-data).\n"
        "Vui lòng thiết lập biến môi trường NEWS_DATA_ROOT hoặc tạo Shortcut từ SharePoint:\n"
        "https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion"
    )


def load_themes(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Đọc từ điển chủ đề (theme) do analyst cấu hình.

    Args:
        path: Đường dẫn tệp JSON; mặc định là `config/themes.json` của plugin.

    Returns:
        Từ điển `theme_key -> {label, group, entities, keywords}`; rỗng nếu thiếu tệp.
    """
    p = path or THEMES_FILE
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("themes", {})


def _to_date(value: str | date | None) -> date | None:
    """Chuyển chuỗi ISO `YYYY-MM-DD` thành `date`, giữ nguyên None."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _ratio(a: float | None, b: float | None) -> float | None:
    """Trả `a / b` làm tròn 2 chữ số, None khi mẫu bằng 0 hoặc thiếu."""
    if a is None or not b:
        return None
    return round(a / b, 2)


def _percentile_rank(value: float | None, sample: list[float]) -> float | None:
    """Tính phân vị (0-100) của `value` trong `sample` theo tỷ lệ phần tử nhỏ hơn hoặc bằng."""
    if value is None or not sample:
        return None
    return round(100.0 * sum(1 for s in sample if s <= value) / len(sample), 1)


class NewsLakehouseClient:
    """Client giao tiếp với Lakehouse qua DuckDB nhúng trên máy trạm cục bộ.

    Phiên DuckDB dựng sẵn hai view: `articles` (OBT kèm `pub_date`, `story_key`, `sent_score`,
    `is_hot`) và `article_entities` (dạng dài `article_id, entity_id, kind`, hợp nhất cột
    `entities` và `symbols`).

    Attributes:
        root: Đường dẫn tới thư mục Lakehouse.
        con: Phiên kết nối DuckDB in-memory.
        themes: Từ điển chủ đề đọc từ `config/themes.json`.
    """

    def __init__(self, root: str | Path | None = None, themes_path: Path | None = None) -> None:
        """Khởi tạo phiên kết nối DuckDB nhúng và dựng các view phân tích.

        Args:
            root: Đường dẫn gốc Lakehouse (nếu None sẽ tự động dò tìm).
            themes_path: Tệp từ điển chủ đề tùy chọn.

        Raises:
            RuntimeError: Nếu chưa cài đặt thư viện duckdb.
            FileNotFoundError: Nếu không tìm thấy thư mục Lakehouse.
        """
        if duckdb is None:
            raise RuntimeError(
                "Chưa cài đặt thư viện 'duckdb'. Vui lòng chạy: pip install duckdb"
            )
        self.root = resolve_lakehouse_root(root)
        self.con = duckdb.connect(database=":memory:")
        self.themes = load_themes(themes_path)
        self._build_views()

    @property
    def parquet_glob(self) -> str:
        """Trả về đường dẫn mẫu khớp tất cả các phân vùng Parquet."""
        return (self.root / "parquet" / "articles" / "*" / "*" / "*.parquet").as_posix()

    def _build_views(self) -> None:
        """Dựng view `raw_articles`, `articles` và `article_entities` trên các tệp Parquet."""
        self.con.execute(
            f"CREATE OR REPLACE VIEW raw_articles AS "
            f"SELECT * FROM read_parquet('{self.parquet_glob}', union_by_name = true)"
        )
        present = {r[0] for r in self.con.execute("DESCRIBE raw_articles").fetchall()}
        cols = []
        for name, typ in REQUIRED_COLUMNS.items():
            cols.append(name if name in present else f"CAST(NULL AS {typ}) AS {name}")
        self.con.execute(f"""
            CREATE OR REPLACE VIEW articles AS
            SELECT
                {", ".join(cols)},
                CAST(substr(published_at, 1, 10) AS DATE) AS pub_date,
                coalesce(nullif(trim(lower(regexp_replace(coalesce(title, ''), '[^\\pL\\pN]+', ' ', 'g'))), ''),
                         article_id) AS story_key,
                CASE lower(coalesce(sentiment, ''))
                    WHEN 'positive' THEN 1 WHEN 'pos' THEN 1
                    WHEN 'negative' THEN -1 WHEN 'neg' THEN -1
                    WHEN 'neutral' THEN 0 WHEN 'neu' THEN 0
                END AS sent_score,
                lower(coalesce(time_sensitivity, '')) IN ('urgent', 'urg', 'today') AS is_hot
            FROM raw_articles
            WHERE published_at IS NOT NULL AND length(published_at) >= 10
        """)
        self.con.execute("""
            CREATE OR REPLACE VIEW article_entities AS
            SELECT DISTINCT article_id, entity_id, split_part(entity_id, ':', 1) AS kind
            FROM (
                SELECT article_id,
                       upper(trim(regexp_replace(e, '\\s*\\[[^\\]]*\\]\\s*$', ''))) AS entity_id
                FROM articles, unnest(entities) AS t(e)
                UNION ALL
                SELECT article_id, 'TICKER:' || upper(trim(s)) AS entity_id
                FROM articles, unnest(symbols) AS t(s)
            )
            WHERE entity_id IS NOT NULL AND entity_id NOT IN ('', 'TICKER:')
        """)

    def _rows(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Thực thi SQL và trả danh sách từ điển với kiểu Python thuần."""
        cur = self.con.execute(sql, params or [])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    def data_range(self) -> dict[str, Any]:
        """Trả khoảng ngày có dữ liệu và số ngày có bài.

        Returns:
            Từ điển `data_from`, `data_to`, `days_with_data`, `n_articles`.
        """
        row = self._rows(
            "SELECT min(pub_date) AS data_from, max(pub_date) AS data_to, "
            "count(DISTINCT pub_date) AS days_with_data, count(*) AS n_articles FROM articles"
        )[0]
        return row

    def _as_of(self, value: str | date | None) -> date:
        """Trả ngày mốc phân tích; mặc định là ngày mới nhất có dữ liệu."""
        d = _to_date(value)
        if d is not None:
            return d
        latest = self.data_range()["data_to"]
        return latest or datetime.now(timezone(timedelta(hours=7))).date()

    def resolve_target(self, target: str) -> dict[str, Any]:
        """Phân giải đối tượng phân tích thành tập thực thể và từ khoá.

        Thứ tự: tên chủ đề trong `themes.json` (có thể kèm tiền tố `theme:`), mã thực thể đầy đủ
        (`KIND:CODE`), mã cổ phiếu 3 ký tự, mã thực thể khớp phần `CODE`, cuối cùng là từ khoá tự do.

        Args:
            target: Chuỗi do analyst nhập (ví dụ `HPG`, `MACRO_GEO:MY`, `dau_tu_cong`, `Dung Quất`).

        Returns:
            Từ điển `label`, `mode`, `entities`, `keywords`.
        """
        raw = target.strip()
        key = raw.lower().removeprefix("theme:")
        if key in self.themes:
            th = self.themes[key]
            return {"label": th.get("label", key), "mode": "theme",
                    "entities": [e.upper() for e in th.get("entities", [])],
                    "keywords": list(th.get("keywords", []))}
        if ":" in raw:
            return {"label": raw.upper(), "mode": "entity", "entities": [raw.upper()], "keywords": []}
        up = raw.upper()
        if len(up) == 3 and up.isalnum():
            return {"label": up, "mode": "ticker", "entities": [f"TICKER:{up}"], "keywords": []}
        code = up.replace(" ", "_")
        hits = [r["entity_id"] for r in self._rows(
            "SELECT DISTINCT entity_id FROM article_entities WHERE split_part(entity_id, ':', 2) = ?",
            [code])]
        if hits:
            return {"label": raw, "mode": "entity", "entities": sorted(hits), "keywords": []}
        return {"label": raw, "mode": "keyword", "entities": [], "keywords": [raw]}

    @staticmethod
    def _match_clause(sel: dict[str, Any], narrow: list[str] | None = None,
                      alias: str = "a") -> tuple[str, list[Any]]:
        """Dựng mệnh đề WHERE chọn bài theo thực thể hoặc từ khoá, có thể thu hẹp bằng từ khoá phụ.

        Args:
            sel: Kết quả `resolve_target`.
            narrow: Từ khoá bắt buộc xuất hiện thêm trong tiêu đề hoặc tóm tắt (điều kiện AND).
            alias: Bí danh bảng `articles` trong câu SQL.

        Returns:
            Bộ (mệnh đề SQL, tham số).
        """
        parts: list[str] = []
        params: list[Any] = []
        if sel["entities"]:
            ph = ", ".join("?" for _ in sel["entities"])
            parts.append(f"{alias}.article_id IN (SELECT article_id FROM article_entities "
                         f"WHERE entity_id IN ({ph}))")
            params.extend(sel["entities"])
        for kw in sel["keywords"]:
            parts.append(f"({alias}.title ILIKE ? OR {alias}.summary ILIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])
        clause = "(" + " OR ".join(parts) + ")" if parts else "FALSE"
        for kw in narrow or []:
            clause += f" AND ({alias}.title ILIKE ? OR {alias}.summary ILIKE ?)"
            params.extend([f"%{kw}%", f"%{kw}%"])
        return clause, params

    def _stories(self, where: str, params: list[Any], order: str = "first_published",
                 limit: int | None = None) -> list[dict[str, Any]]:
        """Gộp các bài thỏa điều kiện thành story (cùng tiêu đề chuẩn hoá) và trả danh sách."""
        sql = (f"SELECT {STORY_COLUMNS} FROM articles a WHERE {where} "
               f"GROUP BY story_key ORDER BY {order}")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self._rows(sql, params)

    def status(self) -> dict[str, Any]:
        """Đọc và kiểm tra trạng thái toàn vẹn của hồ dữ liệu từ latest.json.

        Returns:
            Từ điển thông tin độ tươi, số lượng phân vùng, bản ghi và khoảng ngày có dữ liệu.
        """
        manifest_file = self.root / "_manifest" / "latest.json"
        if not manifest_file.exists():
            return {
                "status": "error",
                "message": f"Thiếu tệp {manifest_file}",
                "root": str(self.root),
            }

        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        latest_day = data.get("day", "")
        updated_at = data.get("updated_at", "")
        total_unique = data.get("total_unique_articles", 0)
        total_partitions = data.get("total_partitions", 0)

        is_stale = False
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                hours_old = (now - dt).total_seconds() / 3600.0
                is_stale = hours_old > 26.0
            except Exception:
                is_stale = False

        rng = self.data_range()
        return {
            "status": "ok",
            "storage_root": str(self.root),
            "latest_day": latest_day,
            "updated_at": updated_at,
            "total_partitions": total_partitions,
            "total_unique_articles": total_unique,
            "is_stale": is_stale,
            "data_from": str(rng["data_from"]) if rng["data_from"] else None,
            "data_to": str(rng["data_to"]) if rng["data_to"] else None,
            "days_with_data": rng["days_with_data"],
        }

    def query_ticker(
        self,
        symbol: str,
        limit: int = 20,
        sentiment: str | None = None,
    ) -> list[dict[str, Any]]:
        """Truy vấn các bài viết liên quan đến mã cổ phiếu, khớp theo `entities` hoặc `symbols`.

        Args:
            symbol: Mã cổ phiếu (ví dụ: 'HPG', 'VCB').
            limit: Số lượng bài viết tối đa.
            sentiment: Lọc theo sắc thái ('pos', 'neg', 'neu') nếu cần.

        Returns:
            Danh sách từ điển các bài báo thỏa mãn điều kiện.
        """
        sym = symbol.strip().upper()
        params: list[Any] = [f"TICKER:{sym}"]
        sent_filter = ""
        if sentiment:
            score = {"pos": 1, "positive": 1, "neg": -1, "negative": -1,
                     "neu": 0, "neutral": 0}.get(sentiment.lower())
            sent_filter = "AND sent_score = ?"
            params.append(score)
        params.append(limit)
        sql = f"""
            SELECT article_id, published_at, title, symbols, summary, key_points, implication,
                   sentiment, time_sensitivity, intent_source, source_domain, url
            FROM articles
            WHERE article_id IN (SELECT article_id FROM article_entities WHERE entity_id = ?)
              {sent_filter}
            ORDER BY published_at DESC
            LIMIT ?
        """
        return self._rows(sql, params)

    def query_urgent(self, limit: int = 30) -> list[dict[str, Any]]:
        """Lọc các bài viết có độ nhạy thời gian khẩn cấp (urgent hoặc today).

        Args:
            limit: Số bài viết tối đa.

        Returns:
            Danh sách bài viết có time_sensitivity trong ('urg', 'today', 'urgent').
        """
        sql = """
            SELECT article_id, published_at, title, symbols, summary, key_points, implication,
                   sentiment, time_sensitivity, source_domain
            FROM articles
            WHERE is_hot
            ORDER BY published_at DESC
            LIMIT ?
        """
        return self._rows(sql, [limit])

    def query_sector_pulse(self) -> list[dict[str, Any]]:
        """Thống kê tổng số tin tức và phân bổ sắc thái của toàn thị trường 14 ngày gần nhất.

        Returns:
            Danh sách thống kê số lượng bài pos, neg, neu theo ngày.
        """
        sql = """
            SELECT
                strftime(pub_date, '%Y-%m-%d') AS trade_date,
                count(*) AS total_articles,
                count(CASE WHEN sent_score = 1 THEN 1 END) AS pos_count,
                count(CASE WHEN sent_score = -1 THEN 1 END) AS neg_count,
                count(CASE WHEN sent_score = 0 THEN 1 END) AS neu_count
            FROM articles
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 14
        """
        return self._rows(sql)

    def query_custom_sql(self, sql: str) -> list[dict[str, Any]]:
        """Thực thi câu lệnh SQL DuckDB tùy biến chỉ đọc.

        Có thể dùng `{articles}` (OBT gốc) hoặc trực tiếp các view `articles`, `article_entities`.

        Args:
            sql: Câu lệnh SQL.

        Returns:
            Danh sách kết quả dạng từ điển.

        Raises:
            ValueError: Nếu câu lệnh chứa từ khóa ghi/xóa dữ liệu hoặc truy cập ngoài.
        """
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "COPY",
                     "ATTACH", "EXPORT", "INSTALL", "LOAD"]
        upper_sql = sql.upper()
        for kw in forbidden:
            if f" {kw} " in f" {upper_sql} ":
                raise ValueError(f"Chỉ cho phép truy vấn đọc dữ liệu, cấm từ khóa: {kw}")

        resolved = sql.replace("{articles}", "raw_articles").replace("{entities}", "article_entities")
        return self._rows(resolved)

    def lookup_entities(self, text: str, limit: int = 20) -> list[dict[str, Any]]:
        """Tìm mã thực thể có chứa chuỗi `text` để analyst chọn đúng đối tượng.

        Args:
            text: Chuỗi cần tìm (không phân biệt hoa thường, khoảng trắng đổi thành `_`).
            limit: Số dòng tối đa.

        Returns:
            Danh sách `entity_id`, `kind`, `n_articles`, `last_date`.
        """
        pattern = f"%{text.strip().upper().replace(' ', '_')}%"
        return self._rows("""
            SELECT e.entity_id, e.kind, count(*) AS n_articles, max(a.pub_date) AS last_date
            FROM article_entities e JOIN articles a USING (article_id)
            WHERE e.entity_id LIKE ?
            GROUP BY 1, 2 ORDER BY n_articles DESC LIMIT ?
        """, [pattern, limit])

    def timeline(self, target: str, date_from: str | None = None, date_to: str | None = None,
                 days: int = 90, grain: str = "week", keywords: list[str] | None = None,
                 max_stories: int = 60) -> dict[str, Any]:
        """Dựng dòng thời gian story và chuỗi thống kê theo kỳ cho một đối tượng.

        Story là nhóm bài cùng tiêu đề chuẩn hoá; khi vượt `max_stories`, giữ các story lan toả
        nhất (nhiều nguồn, khẩn cấp) rồi sắp lại theo thời gian.

        Args:
            target: Mã, thực thể, chủ đề hoặc từ khoá.
            date_from: Ngày bắt đầu; mặc định `date_to - days`.
            date_to: Ngày kết thúc; mặc định ngày mới nhất có dữ liệu.
            days: Độ dài cửa sổ khi không có `date_from`.
            grain: Đơn vị gộp kỳ (`day`, `week`, `month`).
            keywords: Từ khoá thu hẹp (điều kiện AND), dùng cho luận điểm hoặc dự án cụ thể.
            max_stories: Số story tối đa trả về.

        Returns:
            Từ điển `target`, `window`, `coverage`, `periods`, `peak_period`, `stories`,
            `stories_total`.
        """
        if grain not in ("day", "week", "month"):
            raise ValueError("grain phải là day, week hoặc month")
        end = self._as_of(date_to)
        start = _to_date(date_from) or end - timedelta(days=days - 1)
        sel = self.resolve_target(target)
        clause, params = self._match_clause(sel, keywords)
        where = f"{clause} AND a.pub_date BETWEEN ? AND ?"
        params = params + [start, end]

        periods = self._rows(f"""
            SELECT date_trunc('{grain}', a.pub_date)::DATE AS period,
                   count(*) AS n_articles,
                   count(DISTINCT a.story_key) AS n_stories,
                   count(DISTINCT a.source_domain) AS n_sources,
                   count(*) FILTER (WHERE a.sent_score = 1) AS pos,
                   count(*) FILTER (WHERE a.sent_score = -1) AS neg,
                   count(*) FILTER (WHERE a.sent_score = 0) AS neu,
                   count(*) FILTER (WHERE a.is_hot) AS hot,
                   round(avg(a.sent_score), 3) AS net_sent
            FROM articles a WHERE {where}
            GROUP BY 1 ORDER BY 1
        """, params)
        stories = self._stories(where, params)
        total = len(stories)
        if total > max_stories:
            keep = sorted(stories, key=lambda s: (-s["n_sources"], not s["is_hot"],
                                                  s["first_published"]))[:max_stories]
            stories = sorted(keep, key=lambda s: s["first_published"])
        peak = max(periods, key=lambda p: p["n_articles"]) if periods else None
        rng = self.data_range()
        return {
            "target": sel,
            "window": {"from": start, "to": end, "grain": grain, "narrow_keywords": keywords or []},
            "coverage": {"data_from": rng["data_from"], "data_to": rng["data_to"],
                         "window_starts_before_data": bool(rng["data_from"] and start < rng["data_from"])},
            "periods": periods,
            "peak_period": peak,
            "stories_total": total,
            "stories": stories,
        }

    def _top_sector_entities(self, entity_ids: list[str], as_of: date, k: int = 2) -> list[str]:
        """Trả các thực thể ngành (GICS) đồng xuất hiện nhiều nhất với tập thực thể trong 365 ngày."""
        if not entity_ids:
            return []
        ph = ", ".join("?" for _ in entity_ids)
        kinds = ", ".join(f"'{k_}'" for k_ in SECTOR_KINDS)
        rows = self._rows(f"""
            SELECT e2.entity_id, count(*) AS n
            FROM article_entities e1
            JOIN article_entities e2 USING (article_id)
            JOIN articles a USING (article_id)
            WHERE e1.entity_id IN ({ph}) AND e2.kind IN ({kinds})
              AND a.pub_date BETWEEN ? AND ?
            GROUP BY 1 ORDER BY n DESC LIMIT ?
        """, entity_ids + [as_of - timedelta(days=365), as_of, k])
        return [r["entity_id"] for r in rows]

    def event_window(self, target: str, on: str, before: int = 3, after: int = 2,
                     related: bool = True, max_related: int = 15) -> dict[str, Any]:
        """Gom tin quanh một ngày biến động giá để giải thích nguyên nhân.

        Args:
            target: Mã cổ phiếu hoặc đối tượng.
            on: Ngày biến động (`YYYY-MM-DD`).
            before: Số ngày lịch trước ngày biến động.
            after: Số ngày lịch sau ngày biến động.
            related: Có lấy thêm tin ngành và vĩ mô cùng cửa sổ hay không.
            max_related: Số story liên quan tối đa mỗi nhóm.

        Returns:
            Từ điển `target`, `window`, `direct`, `sector_entities`, `sector`, `macro`,
            `no_direct_news`. Mỗi story có `offset_days` so với ngày biến động.
        """
        day = _to_date(on)
        start, end = day - timedelta(days=before), day + timedelta(days=after)
        sel = self.resolve_target(target)
        clause, params = self._match_clause(sel)
        direct = self._stories(f"{clause} AND a.pub_date BETWEEN ? AND ?", params + [start, end])
        direct_keys = {s["story_key"] for s in direct}

        def _offset(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            for r in rows:
                r["offset_days"] = (_to_date(r["first_published"]) - day).days
            return rows

        out: dict[str, Any] = {
            "target": sel,
            "window": {"event_date": day, "from": start, "to": end},
            "direct": _offset(direct),
            "no_direct_news": not direct,
            "sector_entities": [],
            "sector": [],
            "macro": [],
        }
        if not related:
            return out
        sectors = self._top_sector_entities(sel["entities"], day)
        out["sector_entities"] = sectors
        if sectors:
            ph = ", ".join("?" for _ in sectors)
            rows = self._stories(
                f"a.article_id IN (SELECT article_id FROM article_entities WHERE entity_id IN ({ph})) "
                f"AND a.pub_date BETWEEN ? AND ?",
                sectors + [start, end], order="n_sources DESC, first_published")
            out["sector"] = _offset([r for r in rows if r["story_key"] not in direct_keys][:max_related])
        kinds = ", ".join(f"'{k}'" for k in MACRO_KINDS)
        rows = self._stories(
            f"a.article_id IN (SELECT article_id FROM article_entities WHERE kind IN ({kinds})) "
            f"AND a.is_hot AND a.pub_date BETWEEN ? AND ?",
            [day - timedelta(days=1), day], order="n_sources DESC, first_published")
        out["macro"] = _offset([r for r in rows if r["story_key"] not in direct_keys][:max_related])
        return out

    def buzz(self, on: str | None = None, lookback: int = 20, kind: str = "TICKER",
             top: int = 10, min_articles: int = 2, z_min: float = 2.0) -> dict[str, Any]:
        """Xếp hạng thực thể có lượng tin đột biến so với mức nền của chính nó.

        Mức nền là `lookback` ngày có dữ liệu liền trước (ngày thiếu tin của thực thể tính là 0).
        `z = (n_today - mean) / max(sd, 0.5)`.

        Args:
            on: Ngày xét; mặc định ngày mới nhất có dữ liệu.
            lookback: Số ngày có dữ liệu làm mức nền.
            kind: Loại thực thể (`TICKER`, `IND_GICS3`, `MACRO_THEME`... hoặc `ALL`).
            top: Số dòng trả về.
            min_articles: Số bài tối thiểu trong ngày để được xét.
            z_min: Ngưỡng gắn cờ đột biến.

        Returns:
            Từ điển `as_of`, `baseline`, `rows` (mỗi dòng có `z`, `flag`, `n_today`, `mean_n`,
            `hot_share`, `net_sent`, `base_sent`, `sent_delta`, `n_sources`, `n_stories`,
            `top_titles`).
        """
        day = self._as_of(on)
        kind_filter = "" if kind.upper() == "ALL" else "AND e.kind = ?"
        kind_params: list[Any] = [] if kind.upper() == "ALL" else [kind.upper()]
        rows = self._rows(f"""
            WITH days AS (
                SELECT DISTINCT pub_date AS d FROM articles WHERE pub_date < ?
                ORDER BY d DESC LIMIT ?
            ),
            today AS (
                SELECT e.entity_id,
                       count(DISTINCT a.article_id) AS n_today,
                       count(DISTINCT a.story_key) AS n_stories,
                       count(DISTINCT a.source_domain) AS n_sources,
                       round(avg(a.sent_score), 3) AS net_sent,
                       round(avg(CASE WHEN a.is_hot THEN 1.0 ELSE 0.0 END), 3) AS hot_share
                FROM article_entities e JOIN articles a USING (article_id)
                WHERE a.pub_date = ? {kind_filter}
                GROUP BY 1 HAVING count(DISTINCT a.article_id) >= ?
            ),
            base_counts AS (
                SELECT e.entity_id, a.pub_date AS d, count(DISTINCT a.article_id) AS n,
                       sum(a.sent_score) AS s, count(a.sent_score) AS ns
                FROM article_entities e JOIN articles a USING (article_id)
                WHERE a.pub_date IN (SELECT d FROM days)
                  AND e.entity_id IN (SELECT entity_id FROM today)
                GROUP BY 1, 2
            ),
            grid AS (
                SELECT t.entity_id, coalesce(b.n, 0) AS n
                FROM today t CROSS JOIN days
                LEFT JOIN base_counts b ON b.entity_id = t.entity_id AND b.d = days.d
            ),
            stats AS (
                SELECT entity_id, avg(n) AS mean_n, stddev_pop(n) AS sd_n FROM grid GROUP BY 1
            ),
            bsent AS (
                SELECT entity_id, sum(s) / nullif(sum(ns), 0) AS base_sent FROM base_counts GROUP BY 1
            )
            SELECT t.*, round(s.mean_n, 2) AS mean_n, round(s.sd_n, 2) AS sd_n,
                   round(b.base_sent, 3) AS base_sent
            FROM today t
            LEFT JOIN stats s USING (entity_id)
            LEFT JOIN bsent b USING (entity_id)
        """, [day, lookback, day, *kind_params, min_articles])
        n_base = self._rows("SELECT count(DISTINCT pub_date) AS n FROM articles WHERE pub_date < ?",
                            [day])[0]["n"]
        n_base = min(n_base, lookback)
        for r in rows:
            mean = r["mean_n"] if r["mean_n"] is not None else 0.0
            sd = max(r["sd_n"] or 0.0, Z_SD_FLOOR)
            r["z"] = round((r["n_today"] - mean) / sd, 2) if n_base else None
            r["sent_delta"] = (round(r["net_sent"] - r["base_sent"], 3)
                               if r["net_sent"] is not None and r["base_sent"] is not None else None)
            r["flag"] = r["z"] is not None and r["z"] >= z_min
        rows.sort(key=lambda r: (r["z"] if r["z"] is not None else -1e9, r["n_today"]), reverse=True)
        rows = rows[:top]
        for r in rows:
            r["top_titles"] = self._rows("""
                SELECT arg_min(a.title, a.published_at) AS title,
                       count(DISTINCT a.source_domain) AS n_sources,
                       arg_min(a.sentiment, a.published_at) AS sentiment,
                       bool_or(a.is_hot) AS is_hot
                FROM articles a
                WHERE a.pub_date = ? AND a.article_id IN
                      (SELECT article_id FROM article_entities WHERE entity_id = ?)
                GROUP BY a.story_key ORDER BY n_sources DESC LIMIT 3
            """, [day, r["entity_id"]])
        return {
            "as_of": day,
            "baseline": {"days_used": n_base, "days_target": lookback,
                         "sufficient": n_base >= lookback, "z_sd_floor": Z_SD_FLOOR},
            "params": {"kind": kind.upper(), "min_articles": min_articles, "z_min": z_min},
            "rows": rows,
        }

    def sentiment_pulse(self, date_to: str | None = None, days: int = 30, grain: str = "day",
                        target: str | None = None, history_days: int = 365,
                        sectors_top: int = 11) -> dict[str, Any]:
        """Đo tâm lý tin tức theo kỳ, so với phân vị lịch sử, kèm phân rã theo ngành.

        Args:
            date_to: Ngày kết thúc; mặc định ngày mới nhất có dữ liệu.
            days: Độ dài cửa sổ quan sát.
            grain: `day` hoặc `week`.
            target: Đối tượng tùy chọn (ngành, mã, chủ đề); None là toàn thị trường.
            history_days: Độ dài lịch sử dùng tính phân vị.
            sectors_top: Số ngành GICS cấp 3 hiển thị trong phân rã.

        Returns:
            Từ điển `scope`, `window`, `series`, `latest`, `history`, `sectors`.
        """
        if grain not in ("day", "week"):
            raise ValueError("grain phải là day hoặc week")
        end = self._as_of(date_to)
        start = end - timedelta(days=days - 1)
        hist_start = end - timedelta(days=history_days - 1)
        if target:
            sel = self.resolve_target(target)
            clause, cparams = self._match_clause(sel)
        else:
            sel, clause, cparams = None, "TRUE", []

        def _series(s: date, e: date, g: str) -> list[dict[str, Any]]:
            return self._rows(f"""
                SELECT date_trunc('{g}', a.pub_date)::DATE AS period,
                       count(*) AS n_articles,
                       count(*) FILTER (WHERE a.sent_score = 1) AS pos,
                       count(*) FILTER (WHERE a.sent_score = -1) AS neg,
                       count(*) FILTER (WHERE a.sent_score = 0) AS neu,
                       round(avg(a.sent_score), 3) AS net_sent,
                       count(*) FILTER (WHERE a.is_hot) AS hot,
                       count(*) FILTER (WHERE a.is_hot AND a.sent_score = 1) AS hot_pos,
                       count(*) FILTER (WHERE a.is_hot AND a.sent_score = -1) AS hot_neg,
                       round(avg(a.sent_score) FILTER (WHERE a.is_hot), 3) AS hot_net_sent
                FROM articles a WHERE {clause} AND a.pub_date BETWEEN ? AND ?
                GROUP BY 1 ORDER BY 1
            """, cparams + [s, e])

        series = _series(start, end, grain)
        history = [r for r in _series(hist_start, end, grain)
                   if r["n_articles"] >= MIN_DAY_ARTICLES_FOR_PULSE]
        hist_net = [r["net_sent"] for r in history if r["net_sent"] is not None]
        hist_hot = [r["hot_net_sent"] for r in history if r["hot_net_sent"] is not None]
        latest = series[-1] if series else None
        if latest:
            latest = {**latest,
                      "net_sent_pctile": _percentile_rank(latest["net_sent"], hist_net),
                      "hot_net_sent_pctile": _percentile_rank(latest["hot_net_sent"], hist_hot)}
        kinds = ", ".join(f"'{k}'" for k in SECTOR_KINDS)
        sectors = self._rows(f"""
            SELECT e.entity_id, count(*) AS n_articles,
                   count(*) FILTER (WHERE a.sent_score = 1) AS pos,
                   count(*) FILTER (WHERE a.sent_score = -1) AS neg,
                   round(avg(a.sent_score), 3) AS net_sent,
                   count(*) FILTER (WHERE a.is_hot) AS hot
            FROM article_entities e JOIN articles a USING (article_id)
            WHERE e.kind IN ({kinds}) AND {clause} AND a.pub_date BETWEEN ? AND ?
            GROUP BY 1 ORDER BY n_articles DESC LIMIT ?
        """, cparams + [start, end, sectors_top])
        return {
            "scope": sel["label"] if sel else "Toàn thị trường",
            "window": {"from": start, "to": end, "grain": grain},
            "series": series,
            "latest": latest,
            "history": {"from": hist_start, "periods_used": len(hist_net),
                        "min_articles_per_period": MIN_DAY_ARTICLES_FOR_PULSE},
            "sectors": sectors,
        }

    @staticmethod
    def _effective_days(as_of: date, window: int, data_from: date | None) -> int:
        """Trả số ngày lịch của cửa sổ `window` kết thúc ở `as_of` thực sự nằm trong vùng có dữ liệu."""
        if data_from is None:
            return 0
        start = max(as_of - timedelta(days=window - 1), data_from)
        return max((as_of - start).days + 1, 0)

    def theme_trend(self, themes: list[str] | None = None, kind: str | None = None,
                    as_of: str | None = None, top: int = 20) -> dict[str, Any]:
        """Đo tốc độ nóng/nguội của chủ đề qua lượng tin 7, 30 và 90 ngày.

        Trạng thái theo tỷ lệ tốc độ `m7_30 = (n7/7)/(n30/30)`: `Tăng tốc` khi ≥ 1.5,
        `Hạ nhiệt` khi ≤ 0.67, còn lại `Ổn định`; `Ít dữ liệu` khi n90 < 3; `Chưa đủ lịch sử` khi
        dữ liệu chưa phủ quá 7 ngày. Tốc độ chia cho số ngày cửa sổ thực sự có dữ liệu.

        Args:
            themes: Danh sách chủ đề/thực thể; None dùng toàn bộ `themes.json` (hoặc theo `kind`).
            kind: Loại thực thể để xếp hạng thay cho `themes.json` (ví dụ `MACRO_THEME`).
            as_of: Ngày mốc; mặc định ngày mới nhất có dữ liệu.
            top: Số chủ đề tối đa khi dùng `kind`.

        Returns:
            Từ điển `as_of`, `coverage`, `rows` sắp theo `m7_30` giảm dần.
        """
        day = self._as_of(as_of)
        if themes:
            targets = themes
        elif kind:
            targets = [r["entity_id"] for r in self._rows("""
                SELECT e.entity_id, count(*) AS n FROM article_entities e JOIN articles a USING (article_id)
                WHERE e.kind = ? AND a.pub_date BETWEEN ? AND ?
                GROUP BY 1 ORDER BY n DESC LIMIT ?
            """, [kind.upper(), day - timedelta(days=89), day, top])]
        else:
            targets = list(self.themes.keys())
        data_from = self.data_range()["data_from"]
        rows = []
        for t in targets:
            sel = self.resolve_target(t)
            clause, params = self._match_clause(sel)
            d7, d30 = day - timedelta(days=6), day - timedelta(days=29)
            r = self._rows(f"""
                SELECT
                    count(*) FILTER (WHERE a.pub_date >= ?) AS n7,
                    count(*) FILTER (WHERE a.pub_date >= ?) AS n30,
                    count(*) AS n90,
                    count(DISTINCT a.story_key) FILTER (WHERE a.pub_date >= ?) AS stories7,
                    round(avg(a.sent_score) FILTER (WHERE a.pub_date >= ?), 3) AS net_sent7,
                    round(avg(a.sent_score) FILTER (WHERE a.pub_date >= ?), 3) AS net_sent30,
                    max(a.pub_date) AS last_date
                FROM articles a
                WHERE {clause} AND a.pub_date BETWEEN ? AND ?
            """, [d7, d30, d7, d7, d30] + params + [day - timedelta(days=89), day])[0]
            eff7, eff30, eff90 = (self._effective_days(day, n, data_from) for n in (7, 30, 90))
            rate7 = r["n7"] / eff7 if eff7 else None
            rate30 = r["n30"] / eff30 if eff30 else None
            rate90 = r["n90"] / eff90 if eff90 else None
            m7_30 = _ratio(rate7, rate30) if eff30 > eff7 else None
            m30_90 = _ratio(rate30, rate90) if eff90 > eff30 else None
            if eff30 <= eff7:
                state = "Chưa đủ lịch sử"
            elif r["n90"] < 3:
                state = "Ít dữ liệu"
            elif m7_30 is not None and m7_30 >= 1.5:
                state = "Tăng tốc"
            elif m7_30 is not None and m7_30 <= 0.67:
                state = "Hạ nhiệt"
            else:
                state = "Ổn định"
            latest = self._rows(f"""
                SELECT arg_min(a.title, a.published_at) AS title, min(a.published_at) AS published_at,
                       count(DISTINCT a.source_domain) AS n_sources
                FROM articles a WHERE {clause} AND a.pub_date BETWEEN ? AND ?
                GROUP BY a.story_key ORDER BY n_sources DESC, published_at DESC LIMIT 3
            """, params + [day - timedelta(days=6), day])
            rows.append({"theme": t, "label": sel["label"], "mode": sel["mode"], **r,
                         "m7_30": m7_30, "m30_90": m30_90, "state": state, "top_titles_7d": latest})
        rows.sort(key=lambda x: (x["m7_30"] if x["m7_30"] is not None else -1, x["n7"]), reverse=True)
        rows = rows[:top]
        rng = self.data_range()
        span = (rng["data_to"] - rng["data_from"]).days + 1 if rng["data_from"] else 0
        return {"as_of": day,
                "coverage": {"data_from": rng["data_from"], "data_to": rng["data_to"],
                             "span_days": span, "sufficient_for_90d": span >= 90},
                "rows": rows}

    def cooccur(self, target: str, days: int = 365, as_of: str | None = None,
                kinds: list[str] | None = None, top: int = 15,
                keywords: list[str] | None = None) -> dict[str, Any]:
        """Liệt kê thực thể thường xuất hiện cùng đối tượng, kèm độ nâng (lift) so với nền.

        `lift = (n_co / n_target) / (n_entity / n_all)`; lift > 1 nghĩa là thực thể xuất hiện
        cùng đối tượng nhiều hơn mức trung bình của nó.

        Args:
            target: Đối tượng gốc (sự kiện, chủ đề, thực thể địa chính trị, ngành, mã).
            days: Cửa sổ lịch sử.
            as_of: Ngày mốc; mặc định ngày mới nhất có dữ liệu.
            kinds: Loại thực thể cần liệt kê; mặc định `TICKER` và `IND_GICS3`.
            top: Số dòng tối đa mỗi loại.
            keywords: Từ khoá thu hẹp đối tượng gốc.

        Returns:
            Từ điển `target`, `window`, `n_target_articles`, `by_kind` (loại -> danh sách dòng).
        """
        day = self._as_of(as_of)
        start = day - timedelta(days=days - 1)
        kinds = [k.upper() for k in (kinds or ["TICKER", "IND_GICS3"])]
        sel = self.resolve_target(target)
        clause, params = self._match_clause(sel, keywords)
        n_all = self._rows("SELECT count(*) AS n FROM articles WHERE pub_date BETWEEN ? AND ?",
                           [start, day])[0]["n"]
        n_target = self._rows(f"SELECT count(*) AS n FROM articles a WHERE {clause} "
                              f"AND a.pub_date BETWEEN ? AND ?", params + [start, day])[0]["n"]
        exclude = sel["entities"] or ["__none__"]
        ph = ", ".join("?" for _ in exclude)
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for k in kinds:
            rows = self._rows(f"""
                WITH hit AS (
                    SELECT a.* FROM articles a WHERE {clause} AND a.pub_date BETWEEN ? AND ?
                ),
                co AS (
                    SELECT e.entity_id, count(*) AS n_co, count(DISTINCT h.story_key) AS n_stories,
                           max(h.pub_date) AS last_date, round(avg(h.sent_score), 3) AS net_sent,
                           arg_max(h.title, h.published_at) AS latest_title
                    FROM hit h JOIN article_entities e USING (article_id)
                    WHERE e.kind = ? AND e.entity_id NOT IN ({ph})
                    GROUP BY 1
                ),
                base AS (
                    SELECT e.entity_id, count(*) AS n_entity
                    FROM article_entities e JOIN articles a USING (article_id)
                    WHERE e.kind = ? AND a.pub_date BETWEEN ? AND ?
                    GROUP BY 1
                )
                SELECT co.*, base.n_entity FROM co JOIN base USING (entity_id)
                ORDER BY n_co DESC LIMIT ?
            """, params + [start, day, k, *exclude, k, start, day, top])
            for r in rows:
                r["lift"] = (round((r["n_co"] / n_target) / (r["n_entity"] / n_all), 2)
                             if n_target and n_all and r["n_entity"] else None)
            by_kind[k] = rows
        return {"target": sel, "window": {"from": start, "to": day},
                "n_target_articles": n_target, "n_all_articles": n_all, "by_kind": by_kind}

    def brief(self, on: str | None = None, watchlist: list[str] | None = None,
              lookback_days: int = 1, top_spread: int = 10, top_macro: int = 12) -> dict[str, Any]:
        """Dựng gói dữ liệu bản tin sáng ba tầng: watchlist, vĩ mô, tin lan toả nhất.

        Args:
            on: Ngày bản tin; mặc định ngày mới nhất có dữ liệu.
            watchlist: Danh sách mã cổ phiếu hoặc đối tượng theo dõi.
            lookback_days: Số ngày lịch trước `on` được gộp (tin qua đêm).
            top_spread: Số story lan toả nhất.
            top_macro: Số story vĩ mô.

        Returns:
            Từ điển `as_of`, `window`, `watchlist` (đối tượng -> stories), `macro`, `spread`,
            `buzz`.
        """
        day = self._as_of(on)
        start = day - timedelta(days=lookback_days)
        win = [start, day]
        wl: dict[str, Any] = {}
        for t in watchlist or []:
            sel = self.resolve_target(t)
            clause, params = self._match_clause(sel)
            wl[sel["label"]] = self._stories(f"{clause} AND a.pub_date BETWEEN ? AND ?", params + win,
                                             order="is_hot DESC, n_sources DESC, first_published DESC")
        kinds = ", ".join(f"'{k}'" for k in MACRO_KINDS)
        macro = self._stories(
            f"a.article_id IN (SELECT article_id FROM article_entities WHERE kind IN ({kinds})) "
            f"AND a.article_id NOT IN (SELECT article_id FROM article_entities WHERE kind = 'TICKER') "
            f"AND a.pub_date BETWEEN ? AND ?",
            win, order="is_hot DESC, n_sources DESC, first_published DESC", limit=top_macro)
        spread = [s for s in self._stories("a.pub_date BETWEEN ? AND ?", win,
                                           order="n_sources DESC, n_articles DESC, first_published",
                                           limit=top_spread * 2)
                  if s["n_sources"] >= 2][:top_spread]
        buzz = self.buzz(on=str(day), top=5)
        return {"as_of": day, "window": {"from": start, "to": day},
                "watchlist": wl, "macro": macro, "spread": spread,
                "buzz": {"baseline": buzz["baseline"], "rows": [r for r in buzz["rows"] if r["flag"]]}}


def _json_default(obj: Any) -> Any:
    """Chuyển kiểu không tuần tự hoá được (ngày, mảng numpy, Decimal) sang kiểu JSON."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def _dump(data: Any) -> str:
    """Tuần tự hoá kết quả thành JSON tiếng Việt có thụt lề."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=_json_default)


def _format_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    """Định dạng danh sách dòng thành bảng văn bản dễ đọc."""
    if not rows:
        return "Không có dữ liệu phù hợp."
    header = " | ".join(cols)
    sep = " | ".join(["---"] * len(cols))
    lines = [header, sep]
    for r in rows:
        row_str = " | ".join(str(r.get(c, "")).replace("\n", " ")[:60] for c in cols)
        lines.append(row_str)
    return "\n".join(lines)


def _csv(value: str | None) -> list[str] | None:
    """Tách chuỗi phân tách bằng dấu phẩy thành danh sách, bỏ phần tử rỗng."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    """Dựng bộ phân tích tham số dòng lệnh cho mọi lens."""
    parser = argparse.ArgumentParser(
        description="Động cơ DuckDB nhúng truy vấn Lakehouse cho fpts-market-intel"
    )
    parser.add_argument("--root", help="Đường dẫn gốc Lakehouse tùy chọn")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("status", help="Kiểm tra độ tươi dữ liệu và số lượng bài")

    t_p = sub.add_parser("ticker", help="Soi tin tức theo mã cổ phiếu")
    t_p.add_argument("--symbol", required=True, help="Mã cổ phiếu (VD: HPG)")
    t_p.add_argument("--limit", type=int, default=15, help="Số bài tối đa")
    t_p.add_argument("--sentiment", choices=["pos", "neg", "neu"], help="Lọc sắc thái")
    t_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    u_p = sub.add_parser("urgent", help="Lọc tin tức khẩn cấp (urgent, today)")
    u_p.add_argument("--limit", type=int, default=20, help="Số bài tối đa")
    u_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    s_p = sub.add_parser("sector", help="Thống kê sắc thái thị trường 14 ngày")
    s_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    q_p = sub.add_parser("query", help="Chạy câu SQL DuckDB tùy biến")
    q_p.add_argument("--sql", required=True, help="Câu SQL ({articles}, articles, article_entities)")
    q_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    l_p = sub.add_parser("lookup", help="Tìm mã thực thể theo chuỗi")
    l_p.add_argument("--text", required=True, help="Chuỗi cần tìm (VD: lai suat, MY, ngan hang)")
    l_p.add_argument("--limit", type=int, default=20)

    sub.add_parser("themes-list", help="Liệt kê chủ đề cấu hình trong config/themes.json")

    tl = sub.add_parser("timeline", help="Dòng thời gian story theo đối tượng")
    tl.add_argument("--target", required=True, help="Mã, thực thể, chủ đề hoặc từ khoá")
    tl.add_argument("--from", dest="date_from", help="Ngày bắt đầu YYYY-MM-DD")
    tl.add_argument("--to", dest="date_to", help="Ngày kết thúc YYYY-MM-DD")
    tl.add_argument("--days", type=int, default=90, help="Độ dài cửa sổ khi thiếu --from")
    tl.add_argument("--grain", choices=["day", "week", "month"], default="week")
    tl.add_argument("--keywords", help="Từ khoá thu hẹp, phân tách dấu phẩy")
    tl.add_argument("--max-stories", type=int, default=60)

    w = sub.add_parser("window", help="Tin quanh một ngày biến động giá")
    w.add_argument("--target", required=True)
    w.add_argument("--date", required=True, help="Ngày biến động YYYY-MM-DD")
    w.add_argument("--before", type=int, default=3)
    w.add_argument("--after", type=int, default=2)
    w.add_argument("--no-related", action="store_true", help="Bỏ tin ngành và vĩ mô")

    b = sub.add_parser("buzz", help="Thực thể có lượng tin đột biến")
    b.add_argument("--date", help="Ngày xét YYYY-MM-DD")
    b.add_argument("--lookback", type=int, default=20)
    b.add_argument("--kind", default="TICKER", help="TICKER, IND_GICS3, MACRO_THEME, ... hoặc ALL")
    b.add_argument("--top", type=int, default=10)
    b.add_argument("--min-articles", type=int, default=2)
    b.add_argument("--z-min", type=float, default=2.0)

    p = sub.add_parser("pulse", help="Tâm lý tin tức theo kỳ và phân vị lịch sử")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--grain", choices=["day", "week"], default="day")
    p.add_argument("--target", help="Đối tượng tùy chọn; bỏ trống là toàn thị trường")
    p.add_argument("--history-days", type=int, default=365)

    th = sub.add_parser("themes", help="Chủ đề đang nóng lên hay nguội đi (7/30/90 ngày)")
    th.add_argument("--themes", help="Danh sách chủ đề/thực thể, phân tách dấu phẩy")
    th.add_argument("--kind", help="Xếp hạng theo loại thực thể thay cho themes.json")
    th.add_argument("--as-of")
    th.add_argument("--top", type=int, default=20)

    c = sub.add_parser("cooccur", help="Thực thể thường xuất hiện cùng đối tượng")
    c.add_argument("--target", required=True)
    c.add_argument("--days", type=int, default=365)
    c.add_argument("--as-of")
    c.add_argument("--kinds", default="TICKER,IND_GICS3")
    c.add_argument("--top", type=int, default=15)
    c.add_argument("--keywords", help="Từ khoá thu hẹp, phân tách dấu phẩy")

    br = sub.add_parser("brief", help="Gói dữ liệu bản tin sáng ba tầng")
    br.add_argument("--date")
    br.add_argument("--watchlist", help="Mã theo dõi, phân tách dấu phẩy")
    br.add_argument("--lookback-days", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Điểm vào dòng lệnh của lakehouse_client."""
    if sys.platform == "win32" and sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)

    try:
        client = NewsLakehouseClient(root=args.root)
    except Exception as exc:
        print(f"Lỗi khởi tạo Lakehouse Client: {exc}", file=sys.stderr)
        return 1

    try:
        if args.action == "status":
            print(_dump(client.status()))
        elif args.action == "ticker":
            results = client.query_ticker(symbol=args.symbol, limit=args.limit,
                                          sentiment=args.sentiment)
            if args.json:
                print(_dump(results))
            else:
                print(f"--- Kết quả cho mã {args.symbol.upper()} ({len(results)} bài) ---")
                print(_format_table(results, ["published_at", "title", "sentiment", "time_sensitivity"]))
        elif args.action == "urgent":
            results = client.query_urgent(limit=args.limit)
            if args.json:
                print(_dump(results))
            else:
                print(f"--- Danh sách tin tức khẩn cấp ({len(results)} bài) ---")
                print(_format_table(results, ["published_at", "title", "symbols", "sentiment",
                                              "time_sensitivity"]))
        elif args.action == "sector":
            results = client.query_sector_pulse()
            if args.json:
                print(_dump(results))
            else:
                print("--- Thống kê sắc thái thị trường theo ngày ---")
                print(_format_table(results, ["trade_date", "total_articles", "pos_count",
                                              "neg_count", "neu_count"]))
        elif args.action == "query":
            results = client.query_custom_sql(args.sql)
            if args.json:
                print(_dump(results))
            elif results:
                print(_format_table(results, list(results[0].keys())[:5]))
            else:
                print("Truy vấn thành công nhưng không có kết quả.")
        elif args.action == "lookup":
            print(_dump(client.lookup_entities(args.text, args.limit)))
        elif args.action == "themes-list":
            print(_dump(client.themes))
        elif args.action == "timeline":
            print(_dump(client.timeline(args.target, args.date_from, args.date_to, args.days,
                                        args.grain, _csv(args.keywords), args.max_stories)))
        elif args.action == "window":
            print(_dump(client.event_window(args.target, args.date, args.before, args.after,
                                            related=not args.no_related)))
        elif args.action == "buzz":
            print(_dump(client.buzz(args.date, args.lookback, args.kind, args.top,
                                    args.min_articles, args.z_min)))
        elif args.action == "pulse":
            print(_dump(client.sentiment_pulse(args.date_to, args.days, args.grain, args.target,
                                               args.history_days)))
        elif args.action == "themes":
            print(_dump(client.theme_trend(_csv(args.themes), args.kind, args.as_of, args.top)))
        elif args.action == "cooccur":
            print(_dump(client.cooccur(args.target, args.days, args.as_of, _csv(args.kinds),
                                       args.top, _csv(args.keywords))))
        elif args.action == "brief":
            print(_dump(client.brief(args.date, _csv(args.watchlist), args.lookback_days)))
    except Exception as exc:
        print(f"Lỗi truy vấn: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
