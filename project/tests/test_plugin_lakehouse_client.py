"""Bộ kiểm thử đơn vị cho động cơ DuckDB nhúng và lakehouse_client của plugin."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Import module từ thư mục plugin
import sys
PLUGIN_TOOLS_DIR = Path(__file__).resolve().parents[2] / "plugins" / "fpts-market-intel" / "tools"
sys.path.insert(0, str(PLUGIN_TOOLS_DIR))

from lakehouse_client import NewsLakehouseClient, resolve_lakehouse_root


@pytest.fixture
def mock_lakehouse(tmp_path: Path) -> Path:
    """Tạo cấu trúc Lakehouse giả lập với phân vùng Parquet và manifest."""
    root = tmp_path / "news-data"
    manifest_dir = root / "_manifest"
    parquet_dir = root / "parquet" / "articles" / "year=2026" / "month=10"

    manifest_dir.mkdir(parents=True)
    parquet_dir.mkdir(parents=True)

    # 1. Ghi latest.json
    manifest_data = {
        "day": "2026-10-19",
        "updated_at": "2026-10-20T10:00:00+00:00",
        "total_partitions": 1,
        "total_unique_articles": 3,
        "files": [{"path": "parquet/articles/year=2026/month=10/part-20261019.parquet", "rows": 3}],
    }
    (manifest_dir / "latest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # 2. Ghi part-20261019.parquet với 3 bài viết
    schema = pa.schema([
        ("article_id", pa.string()),
        ("published_at", pa.string()),
        ("title", pa.string()),
        ("symbols", pa.list_(pa.string())),
        ("summary", pa.string()),
        ("key_points", pa.string()),
        ("implication", pa.string()),
        ("sentiment", pa.string()),
        ("time_sensitivity", pa.string()),
        ("intent_source", pa.string()),
        ("source_domain", pa.string()),
    ])

    data = {
        "article_id": ["art001", "art002", "art003"],
        "published_at": [
            "2026-10-19T09:00:00+07:00",
            "2026-10-19T10:00:00+07:00",
            "2026-10-19T11:00:00+07:00",
        ],
        "title": [
            "Hòa Phát đạt lợi nhuận tích cực trong quý 3",
            "Vietcombank công bố chính sách mới về lãi suất",
            "Doanh nghiệp nhiệt điện thua kiện hành chính",
        ],
        "symbols": [["HPG"], ["VCB", "MBB"], []],
        "summary": ["Tóm tắt HPG", "Tóm tắt VCB", "Tóm tắt tranh chấp"],
        "key_points": ["Điểm 1", "Điểm 2", "Điểm 3"],
        "implication": ["Hàm ý HPG khả quan", "Hàm ý ngân hàng", "Hàm ý rủi ro"],
        "sentiment": ["positive", "neutral", "negative"],
        "time_sensitivity": ["today", "this_week", "urgent"],
        "intent_source": ["BOTH", "BOTH", "CODE_ONLY"],
        "source_domain": ["cafef.vn", "vietstock.vn", "tinnhanhchungkhoan.vn"],
    }

    table = pa.Table.from_pydict(data, schema=schema)
    pq.write_table(table, parquet_dir / "part-20261019.parquet")

    return root


def test_resolve_lakehouse_root_with_custom_and_env(mock_lakehouse: Path, monkeypatch):
    """Kiểm tra độ ưu tiên khi xác định đường dẫn Lakehouse."""
    # Custom root
    resolved = resolve_lakehouse_root(custom_root=mock_lakehouse)
    assert resolved == mock_lakehouse

    # Env var root
    monkeypatch.setenv("NEWS_DATA_ROOT", str(mock_lakehouse))
    resolved_env = resolve_lakehouse_root()
    assert resolved_env == mock_lakehouse

    # Invalid path throws FileNotFoundError
    with pytest.raises(FileNotFoundError):
        resolve_lakehouse_root(custom_root=mock_lakehouse / "nonexistent")


def test_client_status(mock_lakehouse: Path):
    """Kiểm tra đọc status từ latest.json."""
    client = NewsLakehouseClient(root=mock_lakehouse)
    st = client.status()
    assert st["status"] == "ok"
    assert st["latest_day"] == "2026-10-19"
    assert st["total_unique_articles"] == 3
    assert st["total_partitions"] == 1


def test_client_query_ticker(mock_lakehouse: Path):
    """Kiểm tra lọc bài theo mã cổ phiếu và sentiment."""
    client = NewsLakehouseClient(root=mock_lakehouse)

    # Tìm HPG
    res_hpg = client.query_ticker(symbol="HPG")
    assert len(res_hpg) == 1
    assert res_hpg[0]["title"] == "Hòa Phát đạt lợi nhuận tích cực trong quý 3"
    assert res_hpg[0]["sentiment"] == "positive"

    # Tìm VCB với sentiment = neu (chuẩn hóa mã ngắn)
    res_vcb = client.query_ticker(symbol="VCB", sentiment="neu")
    assert len(res_vcb) == 1
    assert res_vcb[0]["title"] == "Vietcombank công bố chính sách mới về lãi suất"

    # Tìm VCB với sentiment = neg -> Không có kết quả
    res_vcb_neg = client.query_ticker(symbol="VCB", sentiment="neg")
    assert len(res_vcb_neg) == 0

    # Tìm mã không có trong dữ liệu
    res_fpt = client.query_ticker(symbol="FPT")
    assert len(res_fpt) == 0


def test_client_query_urgent(mock_lakehouse: Path):
    """Kiểm tra lọc bài khẩn cấp (today và urgent)."""
    client = NewsLakehouseClient(root=mock_lakehouse)
    res = client.query_urgent()
    # 2 bài: HPG (today) và Doanh nghiệp nhiệt điện (urgent)
    assert len(res) == 2
    titles = [r["title"] for r in res]
    assert "Hòa Phát đạt lợi nhuận tích cực trong quý 3" in titles
    assert "Doanh nghiệp nhiệt điện thua kiện hành chính" in titles


def test_client_query_sector_pulse(mock_lakehouse: Path):
    """Kiểm tra thống kê sắc thái theo ngày."""
    client = NewsLakehouseClient(root=mock_lakehouse)
    pulse = client.query_sector_pulse()
    assert len(pulse) == 1
    row = pulse[0]
    assert row["trade_date"] == "2026-10-19"
    assert row["total_articles"] == 3
    assert row["pos_count"] == 1
    assert row["neg_count"] == 1
    assert row["neu_count"] == 1


def test_client_custom_sql_security(mock_lakehouse: Path):
    """Kiểm tra chạy câu SQL tùy biến và chặn câu lệnh nguy hiểm."""
    client = NewsLakehouseClient(root=mock_lakehouse)

    # SQL an toàn với {articles}
    res = client.query_custom_sql("SELECT count(*) as cnt FROM {articles}")
    assert res[0]["cnt"] == 3

    # Chặn câu lệnh xóa dữ liệu
    with pytest.raises(ValueError, match="Chỉ cho phép truy vấn đọc dữ liệu"):
        client.query_custom_sql("DROP TABLE test")
