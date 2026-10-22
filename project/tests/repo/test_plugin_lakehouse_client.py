"""Bộ kiểm thử đơn vị cho động cơ DuckDB nhúng và lakehouse_client của plugin."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Import module từ thư mục plugin
import sys
PLUGIN_TOOLS_DIR = Path(__file__).resolve().parents[3] / "plugins" / "fpts-market-intel" / "tools"
sys.path.insert(0, str(PLUGIN_TOOLS_DIR))

from lakehouse_client import NewsLakehouseClient, _dump, main, resolve_lakehouse_root


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


def _write_manifest(root: Path, day: str, rows: int) -> None:
    """Ghi `_manifest/latest.json` tối giản cho Lakehouse giả lập."""
    (root / "_manifest").mkdir(parents=True, exist_ok=True)
    (root / "_manifest" / "latest.json").write_text(json.dumps({
        "day": day, "updated_at": "2026-10-07T00:00:00+00:00",
        "total_partitions": 1, "total_unique_articles": rows}), encoding="utf-8")


def _art(aid: str, ts: str, title: str, entities: list[str], sentiment: str = "neutral",
         ts_kind: str = "this_week", source: str = "cafef.vn", symbols: list[str] | None = None) -> dict:
    """Dựng một dòng OBT giả lập."""
    return {"article_id": aid, "url": f"https://x/{aid}", "title": title, "source_domain": source,
            "published_at": ts, "summary": f"Tóm tắt {title}", "key_points": [f"Ý chính {aid}"],
            "implication": f"Hàm ý {aid}", "sentiment": sentiment, "time_sensitivity": ts_kind,
            "entities": entities, "symbols": symbols or [], "intent_source": "agent"}


@pytest.fixture
def rich_lakehouse(tmp_path: Path) -> Path:
    """Tạo Lakehouse nhiều ngày có thực thể, bài trùng giữa các báo và ngày đột biến tin HPG.

    Mức nền: 09-21..09-25 mỗi ngày 1 bài HPG (chỉ có trong `entities`) và 1 bài lãi suất.
    Ngày 10-06: 4 bài HPG (2 bài cùng tiêu đề từ 2 báo), 2 bài NHNN cùng tiêu đề, 1 bài giá thép.
    """
    root = tmp_path / "news-data"
    part = root / "parquet" / "articles" / "year=2026" / "month=10"
    part.mkdir(parents=True)
    hpg = "TICKER:HPG [TICKER]"
    thep = "IND_GICS3:THEP [INDUSTRY_GICS3]"
    ls = "MACRO_THEME:LAI_SUAT [MACRO_THEME]"
    rows = [_art("f0901", "2026-09-01T08:00:00+07:00", "Điều hành tiền tệ đầu tháng 9", [ls])]
    for d in range(21, 26):
        rows.append(_art(f"b{d}", f"2026-09-{d}T09:00:00+07:00", f"Hòa Phát sản xuất ngày {d}", [hpg, thep]))
        rows.append(_art(f"f{d}", f"2026-09-{d}T10:00:00+07:00", f"Thị trường tiền tệ phiên {d}", [ls]))
    rows += [
        _art("e1", "2026-10-06T08:00:00+07:00", "Hòa Phát lãi kỷ lục quý 3", [hpg], "positive", "urgent"),
        _art("e2", "2026-10-06T08:30:00+07:00", "Hòa Phát lãi kỷ lục quý 3", [hpg], "positive", "urgent",
             source="vietstock.vn"),
        _art("e3", "2026-10-06T09:00:00+07:00", "HPG mở rộng Dung Quất", [], "positive", "today",
             symbols=["HPG"]),
        _art("e4", "2026-10-06T09:30:00+07:00", "Cổ đông lớn HPG mua thêm", [hpg], "positive", "today"),
        _art("m1", "2026-10-06T07:00:00+07:00", "NHNN giảm lãi suất điều hành",
             ["INSTITUTION:NHNN [INSTITUTION]", ls], "positive", "urgent"),
        _art("m2", "2026-10-06T07:30:00+07:00", "NHNN giảm lãi suất điều hành",
             ["INSTITUTION:NHNN [INSTITUTION]", ls], "positive", "urgent", source="vneconomy.vn"),
        _art("s1", "2026-10-06T11:00:00+07:00", "Giá thép tăng mạnh", [thep], "negative", "today"),
    ]
    schema = pa.schema([
        ("article_id", pa.string()), ("url", pa.string()), ("title", pa.string()),
        ("source_domain", pa.string()), ("published_at", pa.string()), ("summary", pa.string()),
        ("key_points", pa.list_(pa.string())), ("implication", pa.string()),
        ("sentiment", pa.string()), ("time_sensitivity", pa.string()),
        ("entities", pa.list_(pa.string())), ("symbols", pa.list_(pa.string())),
        ("intent_source", pa.string()),
    ])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), part / "part-20261006.parquet")
    _write_manifest(root, "2026-10-06", len(rows))
    return root


def test_schema_drift_fills_missing_columns(mock_lakehouse: Path):
    """Kiểm tra Parquet thiếu cột `entities`, `url` vẫn dựng được view và truy hồi theo `symbols`."""
    client = NewsLakehouseClient(root=mock_lakehouse)
    ids = {r["entity_id"] for r in client.query_custom_sql("SELECT entity_id FROM article_entities")}
    assert ids == {"TICKER:HPG", "TICKER:VCB", "TICKER:MBB"}


def test_ticker_matches_entities_and_symbols(rich_lakehouse: Path):
    """Kiểm tra mã được truy hồi qua cả `entities` lẫn `symbols`."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    res = client.query_ticker("HPG", limit=50)
    assert len(res) == 9
    assert "e3" in {r["article_id"] for r in res}


def test_resolve_target_modes(rich_lakehouse: Path):
    """Kiểm tra phân giải đối tượng: mã, chủ đề, mã thực thể theo CODE và từ khoá tự do."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    assert client.resolve_target("hpg")["entities"] == ["TICKER:HPG"]
    assert client.resolve_target("lai_suat")["mode"] == "theme"
    assert client.resolve_target("THEP")["entities"] == ["IND_GICS3:THEP"]
    kw = client.resolve_target("Dung Quất")
    assert kw["mode"] == "keyword" and kw["keywords"] == ["Dung Quất"]


def test_timeline_groups_duplicate_titles(rich_lakehouse: Path):
    """Kiểm tra timeline gộp bài cùng tiêu đề thành một story và thu hẹp theo từ khoá."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    tl = client.timeline("HPG", date_from="2026-09-01", date_to="2026-10-06", grain="day")
    assert tl["stories_total"] == 8
    record = next(s for s in tl["stories"] if s["title"] == "Hòa Phát lãi kỷ lục quý 3")
    assert record["n_sources"] == 2 and record["n_articles"] == 2
    assert tl["peak_period"]["n_articles"] == 4
    narrow = client.timeline("HPG", date_from="2026-09-01", date_to="2026-10-06", keywords=["kỷ lục"])
    assert narrow["stories_total"] == 1


def test_buzz_flags_spike_against_baseline(rich_lakehouse: Path):
    """Kiểm tra z-score lượng tin so với mức nền 5 ngày và cờ mức nền chưa đủ."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    res = client.buzz(on="2026-10-06", lookback=5)
    hpg = next(r for r in res["rows"] if r["entity_id"] == "TICKER:HPG")
    assert hpg["n_today"] == 4 and hpg["mean_n"] == 1.0
    assert hpg["z"] == 6.0 and hpg["flag"] is True
    assert hpg["n_sources"] == 2 and hpg["n_stories"] == 3
    assert res["baseline"]["sufficient"] is True
    assert client.buzz(on="2026-10-06", lookback=20)["baseline"]["sufficient"] is False


def test_event_window_direct_sector_macro(rich_lakehouse: Path):
    """Kiểm tra cửa sổ sự kiện trả tin của mã, tin ngành suy từ đồng xuất hiện và tin vĩ mô."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    w = client.event_window("HPG", "2026-10-06", before=1, after=0)
    assert len(w["direct"]) == 3 and w["no_direct_news"] is False
    assert w["sector_entities"] == ["IND_GICS3:THEP"]
    assert [s["title"] for s in w["sector"]] == ["Giá thép tăng mạnh"]
    assert [s["title"] for s in w["macro"]] == ["NHNN giảm lãi suất điều hành"]
    assert client.event_window("HPG", "2026-10-20", before=1, after=0)["no_direct_news"] is True


def test_sentiment_pulse_percentile(rich_lakehouse: Path):
    """Kiểm tra chuỗi tâm lý và phân vị của kỳ mới nhất."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    p = client.sentiment_pulse(date_to="2026-10-06", days=20)
    latest = p["latest"]
    assert latest["period"].isoformat() == "2026-10-06"
    assert latest["n_articles"] == 7 and latest["pos"] == 6 and latest["neg"] == 1
    assert latest["net_sent_pctile"] == 100.0
    assert p["history"]["periods_used"] == 1


def test_theme_trend_rates(rich_lakehouse: Path):
    """Kiểm tra tốc độ 7/30 ngày của chủ đề và nhãn thiếu lịch sử."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    row = client.theme_trend(themes=["lai_suat"], as_of="2026-10-06")["rows"][0]
    assert (row["n7"], row["n30"], row["n90"]) == (2, 7, 8)
    assert row["m7_30"] == round((2 / 7) / (7 / 30), 2)
    assert row["state"] == "Ổn định"
    short = client.theme_trend(themes=["lai_suat"], as_of="2026-09-05")["rows"][0]
    assert short["state"] == "Chưa đủ lịch sử"


def test_cooccur_lift(rich_lakehouse: Path):
    """Kiểm tra thực thể đồng xuất hiện và độ nâng so với nền."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    res = client.cooccur("IND_GICS3:THEP", as_of="2026-10-06", kinds=["TICKER"])
    hpg = res["by_kind"]["TICKER"][0]
    assert hpg["entity_id"] == "TICKER:HPG" and hpg["n_co"] == 5
    assert hpg["lift"] > 1


def test_brief_three_tiers(rich_lakehouse: Path):
    """Kiểm tra bản tin ba tầng: watchlist, vĩ mô không gắn mã, tin nhiều nguồn và mã nóng tin."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    b = client.brief(on="2026-10-06", watchlist=["HPG"])
    assert len(b["watchlist"]["HPG"]) == 3
    assert b["macro"][0]["title"] == "NHNN giảm lãi suất điều hành"
    assert {s["title"] for s in b["spread"]} == {"Hòa Phát lãi kỷ lục quý 3", "NHNN giảm lãi suất điều hành"}
    assert "TICKER:HPG" in {r["entity_id"] for r in b["buzz"]["rows"]}


def test_custom_sql_blocks_copy_and_dumps_lists(rich_lakehouse: Path):
    """Kiểm tra chặn COPY và tuần tự hoá JSON cột danh sách."""
    client = NewsLakehouseClient(root=rich_lakehouse)
    with pytest.raises(ValueError):
        client.query_custom_sql("COPY articles TO 'x.csv'")
    rows = client.query_custom_sql("SELECT key_points, pub_date FROM articles LIMIT 1")
    assert json.loads(_dump(rows))[0]["key_points"]


def test_cli_lens_commands(rich_lakehouse: Path, capsys):
    """Kiểm tra các lệnh lens CLI trả JSON hợp lệ và mã thoát 0."""
    for argv in (["timeline", "--target", "HPG", "--to", "2026-10-06"],
                 ["buzz", "--date", "2026-10-06", "--lookback", "5"],
                 ["window", "--target", "HPG", "--date", "2026-10-06"],
                 ["pulse", "--to", "2026-10-06"],
                 ["themes", "--as-of", "2026-10-06"],
                 ["cooccur", "--target", "THEP", "--as-of", "2026-10-06"],
                 ["brief", "--date", "2026-10-06", "--watchlist", "HPG"],
                 ["lookup", "--text", "thep"]):
        assert main(["--root", str(rich_lakehouse), *argv]) == 0
        json.loads(capsys.readouterr().out)
