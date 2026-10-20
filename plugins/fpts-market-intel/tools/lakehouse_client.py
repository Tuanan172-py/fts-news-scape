"""Động cơ DuckDB nhúng và bộ điều phối truy vấn Lakehouse cho fpts-market-intel."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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


class NewsLakehouseClient:
    """Client giao tiếp với Lakehouse qua DuckDB nhúng trên máy trạm cục bộ.

    Attributes:
        root: Đường dẫn tới thư mục Lakehouse.
        con: Phiên kết nối DuckDB in-memory.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        """Khởi tạo phiên kết nối DuckDB nhúng.

        Args:
            root: Đường dẫn gốc Lakehouse (nếu None sẽ tự động dò tìm).

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

    @property
    def parquet_glob(self) -> str:
        """Trả về đường dẫn mẫu khớp tất cả các phân vùng Parquet."""
        return (self.root / "parquet" / "articles" / "*" / "*" / "*.parquet").as_posix()

    def status(self) -> dict[str, Any]:
        """Đọc và kiểm tra trạng thái toàn vẹn của hồ dữ liệu từ latest.json.

        Returns:
            Từ điển thông tin độ tươi, số lượng phân vùng và bản ghi.
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

        return {
            "status": "ok",
            "storage_root": str(self.root),
            "latest_day": latest_day,
            "updated_at": updated_at,
            "total_partitions": total_partitions,
            "total_unique_articles": total_unique,
            "is_stale": is_stale,
        }

    def query_ticker(
        self,
        symbol: str,
        limit: int = 20,
        sentiment: str | None = None,
    ) -> list[dict[str, Any]]:
        """Truy vấn các bài viết liên quan đến mã cổ phiếu cụ thể.

        Args:
            symbol: Mã cổ phiếu (ví dụ: 'HPG', 'VCB').
            limit: Số lượng bài viết tối đa.
            sentiment: Lọc theo sắc thái ('pos', 'neg', 'neu') nếu cần.

        Returns:
            Danh sách từ điển các bài báo thỏa mãn điều kiện.
        """
        sym = symbol.strip().upper()
        # Chuẩn hóa sắc thái nếu người dùng truyền mã ngắn (pos, neg, neu)
        sent_param = None
        sent_filter = "AND (? IS NULL OR 1=1)"
        if sentiment:
            s_map = {"pos": "positive", "neg": "negative", "neu": "neutral"}
            norm_sent = s_map.get(sentiment.lower(), sentiment.lower())
            sent_filter = "AND (lower(sentiment) = ? OR lower(sentiment) = ?)"
            sent_param = norm_sent

        sql = f"""
            SELECT 
                article_id,
                published_at,
                title,
                symbols,
                summary,
                key_points,
                implication,
                sentiment,
                time_sensitivity,
                intent_source,
                source_domain
            FROM read_parquet('{self.parquet_glob}')
            WHERE list_contains(symbols, ?)
              {sent_filter}
            ORDER BY published_at DESC
            LIMIT ?
        """
        if sentiment:
            s_short = {"positive": "pos", "negative": "neg", "neutral": "neu"}.get(sent_param, sent_param)
            df = self.con.execute(sql, [sym, sent_param, s_short, limit]).df()
        else:
            df = self.con.execute(sql, [sym, None, limit]).df()
        return df.to_dict(orient="records")

    def query_urgent(self, limit: int = 30) -> list[dict[str, Any]]:
        """Lọc các bài viết có độ nhạy thời gian khẩn cấp (urg hoặc today).

        Args:
            limit: Số bài viết tối đa.

        Returns:
            Danh sách bài viết có time_sensitivity trong ('urg', 'today', 'urgent').
        """
        sql = f"""
            SELECT 
                article_id,
                published_at,
                title,
                symbols,
                summary,
                key_points,
                implication,
                sentiment,
                time_sensitivity,
                source_domain
            FROM read_parquet('{self.parquet_glob}')
            WHERE lower(time_sensitivity) IN ('urg', 'today', 'urgent')
            ORDER BY published_at DESC
            LIMIT ?
        """
        df = self.con.execute(sql, [limit]).df()
        return df.to_dict(orient="records")

    def query_sector_pulse(self) -> list[dict[str, Any]]:
        """Thống kê tổng số tin tức và phân bổ sắc thái của toàn thị trường.

        Returns:
            Danh sách thống kê số lượng bài pos, neg, neu theo ngày.
        """
        sql = f"""
            SELECT 
                strftime(CAST(published_at AS TIMESTAMP), '%Y-%m-%d') AS trade_date,
                count(*) AS total_articles,
                count(CASE WHEN lower(sentiment) IN ('pos', 'positive') THEN 1 END) AS pos_count,
                count(CASE WHEN lower(sentiment) IN ('neg', 'negative') THEN 1 END) AS neg_count,
                count(CASE WHEN lower(sentiment) IN ('neu', 'neutral') THEN 1 END) AS neu_count
            FROM read_parquet('{self.parquet_glob}')
            WHERE published_at IS NOT NULL AND published_at != ''
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 14
        """
        df = self.con.execute(sql).df()
        return df.to_dict(orient="records")

    def query_custom_sql(self, sql: str) -> list[dict[str, Any]]:
        """Thực thi câu lệnh SQL DuckDB tùy biến an toàn.

        Args:
            sql: Câu lệnh SQL (có thể dùng {articles} thay cho read_parquet(...)).

        Returns:
            Danh sách kết quả dạng từ điển.

        Raises:
            ValueError: Nếu câu lệnh chứa từ khóa ghi/xóa dữ liệu.
        """
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"]
        upper_sql = sql.upper()
        for kw in forbidden:
            if f" {kw} " in f" {upper_sql} ":
                raise ValueError(f"Chỉ cho phép truy vấn đọc dữ liệu, cấm từ khóa: {kw}")

        resolved = sql.replace("{articles}", f"read_parquet('{self.parquet_glob}')")
        df = self.con.execute(resolved).df()
        return df.to_dict(orient="records")


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


def main(argv: list[str] | None = None) -> int:
    """Điểm vào dòng lệnh của lakehouse_client."""
    if sys.platform == "win32" and sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Động cơ DuckDB nhúng truy vấn Lakehouse cho fpts-market-intel"
    )
    parser.add_argument("--root", help="Đường dẫn gốc Lakehouse tùy chọn")

    sub = parser.add_subparsers(dest="action", required=True)

    # status
    sub.add_parser("status", help="Kiểm tra độ tươi dữ liệu và số lượng bài")

    # ticker
    t_p = sub.add_parser("ticker", help="Soi tin tức theo mã cổ phiếu")
    t_p.add_argument("--symbol", required=True, help="Mã cổ phiếu (VD: HPG)")
    t_p.add_argument("--limit", type=int, default=15, help="Số bài tối đa")
    t_p.add_argument("--sentiment", choices=["pos", "neg", "neu"], help="Lọc sắc thái")
    t_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    # urgent
    u_p = sub.add_parser("urgent", help="Lọc tin tức khẩn cấp (urg, today)")
    u_p.add_argument("--limit", type=int, default=20, help="Số bài tối đa")
    u_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    # sector
    s_p = sub.add_parser("sector", help="Đo lường xung lực sắc thái thị trường")
    s_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    # query
    q_p = sub.add_parser("query", help="Chạy câu SQL DuckDB tùy biến")
    q_p.add_argument("--sql", required=True, help="Câu lệnh SQL ({articles} đại diện cho bảng)")
    q_p.add_argument("--json", action="store_true", help="Xuất dạng JSON")

    args = parser.parse_args(argv)

    try:
        client = NewsLakehouseClient(root=args.root)
    except Exception as exc:
        print(f"Lỗi khởi tạo Lakehouse Client: {exc}", file=sys.stderr)
        return 1

    if args.action == "status":
        st = client.status()
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0

    if args.action == "ticker":
        results = client.query_ticker(
            symbol=args.symbol,
            limit=args.limit,
            sentiment=args.sentiment,
        )
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            cols = ["published_at", "title", "sentiment", "time_sensitivity"]
            print(f"--- Kết quả cho mã {args.symbol.upper()} ({len(results)} bài) ---")
            print(_format_table(results, cols))
        return 0

    if args.action == "urgent":
        results = client.query_urgent(limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            cols = ["published_at", "title", "symbols", "sentiment", "time_sensitivity"]
            print(f"--- Danh sách tin tức khẩn cấp ({len(results)} bài) ---")
            print(_format_table(results, cols))
        return 0

    if args.action == "sector":
        results = client.query_sector_pulse()
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            cols = ["trade_date", "total_articles", "pos_count", "neg_count", "neu_count"]
            print("--- Thống kê sắc thái thị trường theo ngày ---")
            print(_format_table(results, cols))
        return 0

    if args.action == "query":
        try:
            results = client.query_custom_sql(args.sql)
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                if results:
                    cols = list(results[0].keys())[:5]
                    print(_format_table(results, cols))
                else:
                    print("Truy vấn thành công nhưng không có kết quả.")
            return 0
        except Exception as exc:
            print(f"Lỗi truy vấn SQL: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
