"""Verify multi-scope NER, normalized Entity Database storage, and Lakehouse skill workflows."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
PLUGIN_TOOLS_DIR = REPO_ROOT / "plugins" / "fpts-market-intel" / "tools"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PLUGIN_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_TOOLS_DIR))

from lakehouse_client import NewsLakehouseClient, request_priority_refresh  # noqa: E402
from scripts import build_entities  # noqa: E402
from scripts.article_expand import build_l1_output, collect_code_hits  # noqa: E402
from src.agent.entities import EntityRegistry, _apply_runtime_overlays, load_registry  # noqa: E402
from src.agent.intent_resolve import IntentResolver, reconcile  # noqa: E402
from src.agent.l1_router import check_l1_dod  # noqa: E402
from src.core.models import Article  # noqa: E402
from src.db.store import ArticleStore  # noqa: E402
from src.export.user_output import UserOutputWriter  # noqa: E402
from src.ops.config import load_config, resolve_paths  # noqa: E402
from src.ops.sensor import SensorReading, decide, read_pending  # noqa: E402
from src.ops.store import VN_TZ, OpsStore  # noqa: E402
from src.ops.wave_flow import WaveSpec, WaveSteps  # noqa: E402
from src.research_db import master, production  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    """Build an isolated runtime EntityRegistry augmented with edge-case securities for tests."""
    load_registry.cache_clear()
    base = list(load_registry().entities.values())
    extra_seeds = [
        {
            "entity_id": "ETF:E12",
            "type": "ETF",
            "code": "E12",
            "canonical_name": "CTCP Xây dựng Điện VNECO 12",
            "aliases": ["CTCP Xây dựng Điện VNECO 12"],
            "attributes": {"tier": 1, "is_active": True},
            "sources": ["tests"],
        },
        {
            "entity_id": "TICKER:VHM",
            "type": "TICKER",
            "code": "VHM",
            "canonical_name": "CTCP Vinhomes",
            "aliases": ["CTCP Vinhomes"],
            "attributes": {"tier": 1, "is_active": True},
            "sources": ["tests"],
        },
        {
            "entity_id": "TICKER:OGC",
            "type": "TICKER",
            "code": "OGC",
            "canonical_name": "CTCP Tập đoàn Đại Dương",
            "aliases": ["CTCP Tập đoàn Đại Dương", "Đại Dương"],
            "attributes": {"tier": 1, "is_active": True},
            "sources": ["tests"],
        },
        {
            "entity_id": "TICKER:MSB",
            "type": "TICKER",
            "code": "MSB",
            "canonical_name": "Ngân hàng TMCP Hàng Hải Việt Nam",
            "aliases": ["Ngân hàng TMCP Hàng Hải Việt Nam"],
            "attributes": {"tier": 1, "is_active": True},
            "sources": ["tests"],
        },
        {
            "entity_id": "TICKER:PGD",
            "type": "TICKER",
            "code": "PGD",
            "canonical_name": "CTCP Phân phối Khí thấp áp Dầu khí Việt Nam",
            "aliases": ["Khí thấp áp"],
            "attributes": {"tier": 1, "is_active": True},
            "sources": ["tests"],
        },
        {
            "entity_id": "INSTITUTION:BO_TAI_CHINH",
            "type": "INSTITUTION",
            "code": "BO_TAI_CHINH",
            "canonical_name": "Bộ Tài chính",
            "aliases": ["Bộ Tài chính", "BTC"],
            "attributes": {"category": "institution"},
            "sources": ["tests"],
        },
        {
            "entity_id": "ASSET_CLASS:TIEN_MA_HOA",
            "type": "ASSET_CLASS",
            "code": "TIEN_MA_HOA",
            "canonical_name": "Tiền mã hóa",
            "aliases": ["Tiền mã hóa", "Bitcoin", "BTC"],
            "attributes": {"category": "asset"},
            "sources": ["tests"],
        },
    ]
    return EntityRegistry(_apply_runtime_overlays(base + extra_seeds))


@pytest.fixture(scope="module")
def resolver(registry):
    """Build a shared IntentResolver over the loaded registry."""
    return IntentResolver(registry)


def test_strict_yaml_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    """Reject duplicate YAML keys in alias configuration files."""
    dup_yaml = tmp_path / "dup.yaml"
    dup_yaml.write_text("VIC:\n  - Vinhomes\nVIC:\n  - VinFast\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate YAML key 'VIC'"):
        build_entities.load_strict_yaml(dup_yaml)

    # Production YAML files must parse cleanly with zero duplicate keys.
    tickers_data = build_entities.load_strict_yaml(
        PROJECT_ROOT / "config" / "entities" / "aliases" / "tickers.yaml"
    )
    unlisted_data = build_entities.load_strict_yaml(
        PROJECT_ROOT / "config" / "entities" / "aliases" / "unlisted_orgs.yaml"
    )
    assert "Vinpearl" in tickers_data["VIC"]
    assert "Vinhomes" in tickers_data["VHM"]
    assert "Thế Giới Di Động" in tickers_data["MWG"]
    assert "EVN" in unlisted_data


def test_classify_code_and_runtime_catalog_overlays(registry) -> None:
    """Classify E12 as a stock ticker and expose unlisted organizations at runtime."""
    assert build_entities.classify_code("E12", set()) == "STOCK"
    assert build_entities.classify_code("E1VFVN30", {"E1VFVN30"}) == "ETF"
    assert build_entities.classify_code("FUEVFVND", set()) == "ETF"

    assert registry.get("TICKER:E12") is not None
    assert registry.get("ETF:E12") is None
    assert registry.get("UNLISTED_ORG:EVN") is not None
    assert registry.get("UNLISTED_ORG:SUN_GROUP") is not None
    vinfast = registry.get("UNLISTED_ORG:VINFAST")
    assert vinfast is not None
    assert vinfast["attributes"]["parent_entity_id"] == "TICKER:VIC"


def test_entity_detector_precision_guards_and_tone_normalization(registry) -> None:
    """Enforce tone normalization, bank PGD guards, and BTC context disambiguation."""
    # Both old ("Hoà") and new ("Hòa") tone placements match TICKER:HPG.
    ids_old = {d["entity_id"] for d in registry.detect("Tập đoàn Hoà Phát tăng sản lượng thép")}
    ids_new = {d["entity_id"] for d in registry.detect("Tập đoàn Hòa Phát tăng sản lượng thép")}
    assert "TICKER:HPG" in ids_old
    assert "TICKER:HPG" in ids_new

    # Merged YAML aliases work immediately via runtime overlay.
    ids_vp = {d["entity_id"] for d in registry.detect("Vinpearl khai trương khu nghỉ dưỡng mới")}
    assert "TICKER:VIC" in ids_vp
    ids_vhm = {d["entity_id"] for d in registry.detect("Vinhomes mở bán đại dự án mới")}
    assert "TICKER:VHM" in ids_vhm
    ids_mwg = {d["entity_id"] for d in registry.detect("Điện Máy Xanh mở rộng chuỗi cửa hàng")}
    assert "TICKER:MWG" in ids_mwg

    # Lowercase 2-word Vietnamese homophones without diacritics are blocked, while Proper Nouns pass.
    ids_prop = {d["entity_id"] for d in registry.detect("Tập đoàn Hoa Phat báo lãi lớn")}
    assert "TICKER:HPG" in ids_prop

    # Generic stoplist blocks "Đại Dương" -> OGC and "Quốc Dân" -> NVB.
    ids_ocean = {d["entity_id"] for d in registry.detect("Kinh tế đại dương xanh phát triển bền vững")}
    assert "TICKER:OGC" not in ids_ocean

    # Expanded 27-bank PGD guard blocks MSB/ACB/LPB branch disclosures from matching TICKER:PGD.
    ids_msb = {d["entity_id"] for d in registry.detect("MSB: Thông báo thay đổi địa điểm PGD Đống Đa")}
    assert "TICKER:MSB" in ids_msb
    assert "TICKER:PGD" not in ids_msb

    # BTC disambiguation separates fiscal policy, crypto, and organizing committees.
    ids_fiscal = {d["entity_id"] for d in registry.detect("BTC ban hành thông tư hướng dẫn thuế thu nhập")}
    assert "INSTITUTION:BO_TAI_CHINH" in ids_fiscal
    assert "ASSET_CLASS:TIEN_MA_HOA" not in ids_fiscal

    ids_crypto = {d["entity_id"] for d in registry.detect("Giá BTC vượt mốc kỷ lục trên thị trường crypto")}
    assert "ASSET_CLASS:TIEN_MA_HOA" in ids_crypto
    assert "INSTITUTION:BO_TAI_CHINH" not in ids_crypto

    ids_committee = {d["entity_id"] for d in registry.detect("Ban tổ chức (BTC) công bố lịch thi đấu giải chạy")}
    assert "ASSET_CLASS:TIEN_MA_HOA" not in ids_committee
    assert "INSTITUTION:BO_TAI_CHINH" not in ids_committee


def test_multi_scope_resolver_and_l1_v1_1_dod(registry, resolver) -> None:
    """Preserve title, body, inferred industry, and parent-linked entities through DoD v1.1."""
    # ETF under TIC and corporate-prefix-stripped COM resolve cleanly.
    r_etf = resolver.resolve_one("E1VFVN30", "TIC", title="Quỹ E1VFVN30 hút vốn")
    assert r_etf.entity_id == "ETF:E1VFVN30"

    r_corp = resolver.resolve_one("Tập đoàn Hòa Phát", "COM", title="Tập đoàn Hòa Phát báo lãi")
    assert r_corp.entity_id == "TICKER:HPG"

    title = "Ngành thép phục hồi mạnh trong quý 4"
    paragraphs = [
        "Tập đoàn Hòa Phát ghi nhận sản lượng tiêu thụ thép xây dựng tăng trưởng 28% so với cùng kỳ.",
        "Hòa Phát và VinFast ký thỏa thuận cung ứng vật liệu chế tạo tại khu liên hợp Dung Quất.",
        "Bên cạnh đó, cổ phiếu HSG cũng thu hút dòng tiền khối ngoại trong phiên giao dịch cuối tuần.",
    ]
    llm_pairs = [
        ["Hòa Phát", "COM"],
        ["VinFast", "COM"],
        ["Thép", "IND"],
        ["ông Trần Đình Long", "PER"],
    ]
    resolved = resolver.resolve_many(
        llm_pairs,
        title=title,
        paragraphs=paragraphs,
        cited_indices={0},
    )
    code_hits = collect_code_hits(title, paragraphs, registry)
    labels = reconcile(resolved, set(code_hits))
    out = build_l1_output(
        "art_multiscope_01",
        title,
        resolved,
        labels,
        code_hits=code_hits,
        agent_provider="agy",
        model_used="test-model",
    )

    assert out["l1_output_version"] == "1.1"
    passed, reasons = check_l1_dod(out, title, registry=registry, paragraphs=paragraphs)
    assert passed, reasons

    by_eid = {e["entity_id"]: e for e in out["entities"]}
    # HPG appears in body paragraphs 0 and 1 (cited) -> primary, HIGH.
    assert by_eid["TICKER:HPG"]["scope"] == "body"
    assert by_eid["TICKER:HPG"]["role"] == "primary"
    assert by_eid["TICKER:HPG"]["provenance"] == "BOTH"

    # VinFast resolves to UNLISTED_ORG:VINFAST and propagates parent TICKER:VIC.
    assert "UNLISTED_ORG:VINFAST" in by_eid
    assert "TICKER:VIC" in by_eid

    # HSG was only matched by deterministic code scan in paragraph 2 -> CODE_ONLY, mentioned.
    assert by_eid["TICKER:HSG"]["provenance"] == "CODE_ONLY"
    assert by_eid["TICKER:HSG"]["role"] == "mentioned"
    assert by_eid["TICKER:HSG"]["confidence_tier"] == "LOW"

    # Open-set person surface is retained in unlisted_candidates.
    assert "ông Trần Đình Long" in out["unlisted_candidates"]


def test_master_db_migration_candidates_log_and_user_routing(tmp_path: Path, monkeypatch, registry) -> None:
    """Migrate master DB schema, log unlisted candidates, and filter user output by primary role."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(data_dir))
    monkeypatch.setattr(master, "DEFAULT_MAX_RETRACT_RATIO", 1.0)

    # Pre-create an older 8-column article_entities table to verify in-place migration.
    master_db = data_dir / "research_db" / "news_research_master.db"
    master_db.parent.mkdir(parents=True, exist_ok=True)
    legacy_conn = sqlite3.connect(master_db)
    legacy_conn.executescript(
        """
        CREATE TABLE articles (article_id TEXT PRIMARY KEY, published_date TEXT);
        CREATE TABLE article_entities (
            article_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            surface TEXT,
            entity_id TEXT,
            type TEXT NOT NULL,
            method TEXT,
            in_list INTEGER NOT NULL,
            confidence REAL,
            PRIMARY KEY (article_id, ordinal)
        );
        """
    )
    legacy_conn.close()
    # Recreate cleanly via open_master after testing column migration on article_entities.
    migrated = master.open_master(master_db)
    cols = {r[1] for r in migrated.execute("PRAGMA table_info(article_entities)")}
    migrated.close()
    assert {"scope", "role", "provenance", "confidence_tier", "first_para_idx"} <= cols
    master_db.unlink()

    ops_db_path = data_dir / "monocle.db"
    store = ArticleStore(db_path=ops_db_path)
    ts = "2026-11-11T09:30:00+07:00"
    store.insert(Article(
        url="https://cafef.vn/hpg-body-test",
        title=" Triển vọng ngành thép cuối năm",
        source_domain="cafef.vn",
        content_text="Hòa Phát dẫn đầu thị phần thép xây dựng trong khi HSG xuất khẩu tôn mạ.",
        fetched_at=ts,
        published_at=ts,
        symbols=["HCM"],  # Simulated noisy scraper symbol that must stay isolated.
    ))
    conn = sqlite3.connect(ops_db_path)
    aid = conn.execute("SELECT url_title_hash FROM articles").fetchone()[0]
    conn.close()

    ag_doc = {
        "article_id": aid,
        "summary": "Ngành thép phục hồi nhờ đầu tư công.",
        "key_points": ["Sản lượng Hòa Phát tăng mạnh trong quý 4"],
        "implication": "Biên lợi nhuận gộp của doanh nghiệp đầu ngành cải thiện rõ rệt.",
        "sentiment": "positive",
        "time_sensitivity": "today",
        "citations": ["Hòa Phát dẫn đầu thị phần thép xây dựng trong khi HSG xuất khẩu tôn mạ."],
    }
    l1_doc = {
        "l1_output_version": "1.1",
        "article_id": aid,
        "title": "Triển vọng ngành thép cuối năm",
        "recognized": True,
        "entities": [
            {
                "surface": "Hòa Phát",
                "entity_id": "TICKER:HPG",
                "type": "TICKER",
                "method": "alias",
                "in_list": True,
                "scope": "body",
                "role": "primary",
                "provenance": "BOTH",
                "confidence_tier": "HIGH",
                "first_para_idx": 0,
            },
            {
                "surface": "HSG",
                "entity_id": "TICKER:HSG",
                "type": "TICKER",
                "method": "exact_code",
                "in_list": True,
                "scope": "body",
                "role": "mentioned",
                "provenance": "CODE_ONLY",
                "confidence_tier": "LOW",
                "first_para_idx": 0,
            },
        ],
        "categories": {
            "ticker_company": "done", "etf_fund": "none", "index": "none", "exchange": "none",
            "industry_sector": "none", "macro_geo": "none", "asset_class": "none", "institution": "none",
        },
        "unlisted_candidates": ["Hiệp hội Thép Việt Nam"],
        "citations": [{"source_span": "Hòa Phát"}],
        "processing_metadata": {
            "agent_provider": "agy",
            "model_used": "test",
            "timestamp": ts,
            "intent_source": {"TICKER:HPG": "BOTH", "TICKER:HSG": "CODE_ONLY"},
        },
    }
    store.insert_agent_output({
        "article_id": aid, "raw_sha256": "sha1",
        "output_json": json.dumps(ag_doc, ensure_ascii=False),
        "dod_pass": 1, "agent_provider": "agy", "created_at": ts,
    })
    store.insert_l1_output({
        "article_id": aid,
        "output_json": json.dumps(l1_doc, ensure_ascii=False),
        "dod_pass": 1, "created_at": ts, "l1_source": "agent",
    })

    target_news = tmp_path / "FRA - Data" / "news"
    pub_out = production.publish(ops_db_path, target=target_news)
    assert pub_out.status == "published", pub_out.message

    m_conn = master.open_master(master_db)
    try:
        cand_row = m_conn.execute(
            "SELECT surface_sample, article_count FROM entity_candidates_log"
        ).fetchone()
        assert cand_row == ("Hiệp hội Thép Việt Nam", 1)
    finally:
        m_conn.close()

    # Verify UserOutputWriter._entity_ids routes primary HPG and drops CODE_ONLY/mentioned HSG.
    writer = UserOutputWriter(store, registry=registry, output_root=tmp_path / "users_out")
    routed_ids = writer._entity_ids(json.dumps(l1_doc, ensure_ascii=False))
    assert routed_ids == {"TICKER:HPG"}

    # Verify Lakehouse client isolates noisy scraper `symbols=["HCM"]` on GOLD rows and
    # filters mentioned/CODE_ONLY by default.
    client_default = NewsLakehouseClient(root=target_news)
    assert client_default.query_ticker("HCM") == []
    assert len(client_default.query_ticker("HPG")) == 1
    assert client_default.query_ticker("HSG") == []

    # ADR-0027 with ADR-0031.D4 as amended: `entities` keeps only ids the model named, so
    # include_mentions=True never returns the CODE_ONLY HSG; the matcher's HSG stays readable
    # through `intent_code`.
    client_all = NewsLakehouseClient(root=target_news, include_mentions=True)
    assert client_all.query_ticker("HSG") == []
    code_rows = client_all.query_custom_sql(
        "SELECT intent_code, entities FROM {articles} WHERE intent_code LIKE '%HSG%'")
    assert len(code_rows) == 1
    assert not any("HSG" in str(e) for e in (code_rows[0]["entities"] or []))


def test_lakehouse_client_target_resolution_accents_security_and_intraday_delta(tmp_path: Path) -> None:
    """Verify 3-char trap fix, Vietnamese tone/accent search, SQL sandbox, and Intraday Delta bridge."""
    root = tmp_path / "lakehouse"
    part_dir = root / "parquet" / "articles" / "year=2026" / "month=11"
    part_dir.mkdir(parents=True)
    (root / "_manifest").mkdir(parents=True)
    (root / "_manifest" / "latest.json").write_text(
        json.dumps({
            "day": "2026-11-10",
            "updated_at": "2026-11-10T10:00:00+07:00",
            "total_partitions": 1,
            "total_unique_articles": 1,
        }),
        encoding="utf-8",
    )
    pq_rows = [{
        "article_id": "pq_1",
        "url": "https://a.vn/1",
        "title": "Giá dầu thế giới giảm mạnh khi GDP quý 3 tăng",
        "source_domain": "a.vn",
        "published_at": "2026-11-10T08:00:00+07:00",
        "summary": "Tập đoàn Hoà Phát hưởng lợi từ chi phí năng lượng đầu vào hạ nhiệt.",
        "key_points": ["Sản lượng Dung Quất đạt công suất tối đa"],
        "implication": "Dòng tiền cổ phiếu ngành thép tích cực.",
        "sentiment": "positive",
        "time_sensitivity": "today",
        "entities": ["TICKER:HPG [TICKER|primary|BOTH]"],
        "symbols": ["HCM"],
        "intent_source": "BOTH:1",
        "gold_status": "GOLD",
    }]
    schema = pa.schema([
        ("article_id", pa.string()), ("url", pa.string()), ("title", pa.string()),
        ("source_domain", pa.string()), ("published_at", pa.string()), ("summary", pa.string()),
        ("key_points", pa.list_(pa.string())), ("implication", pa.string()),
        ("sentiment", pa.string()), ("time_sensitivity", pa.string()),
        ("entities", pa.list_(pa.string())), ("symbols", pa.list_(pa.string())),
        ("intent_source", pa.string()), ("gold_status", pa.string()),
    ])
    pq.write_table(pa.Table.from_pylist(pq_rows, schema=schema), part_dir / "part-20261110.parquet")

    # Populate a newer intraday article in local news_research_master.db not yet in Parquet.
    master_db = tmp_path / "news_research_master.db"
    m_conn = master.open_master(master_db)
    m_conn.execute(
        """
        INSERT INTO articles (
            article_id, url, title, source_domain, published_at, fetched_at, published_date,
            summary, key_points_json, implication, sentiment, time_sensitivity, citations_json,
            symbols, categories, raw_sha256, analysis_provider, analysis_model, analysis_at,
            entity_at, entity_source, inherited_from, src_agent_output_id, src_l1_output_id,
            gate_version, synced_at
        ) VALUES (
            'delta_2', 'https://a.vn/2', 'FPT ký hợp đồng AI lớn tại Nhật Bản', 'a.vn',
            '2026-11-11T10:15:00+07:00', '2026-11-11T10:16:00+07:00', '2026-11-11',
            'Doanh thu mảng công nghệ nước ngoài tăng 30%.', '["Hợp đồng 100 triệu USD"]',
            'Tác động tích cực lên tăng trưởng lợi nhuận năm 2027.', 'positive', 'urgent',
            '["FPT ký hợp đồng AI lớn tại Nhật Bản"]', 'FPT', '', 'sha2', 'agy', 'm',
            '2026-11-11T10:20:00+07:00', '2026-11-11T10:20:00+07:00', 'agent', NULL, 1, 1,
            'research-gate/1', '2026-11-11T10:21:00+07:00'
        )
        """
    )
    m_conn.execute(
        """
        INSERT INTO article_entities (
            article_id, ordinal, surface, entity_id, type, method, in_list, confidence,
            scope, role, provenance, confidence_tier, first_para_idx
        ) VALUES ('delta_2', 0, 'FPT', 'TICKER:FPT', 'TICKER', 'exact_code', 1, 0.99,
                  'title', 'primary', 'BOTH', 'HIGH', -1)
        """
    )
    m_conn.commit()
    m_conn.close()

    client = NewsLakehouseClient(root=root, master_db=master_db)
    st = client.status()
    assert st["intraday_delta_rows"] == 1
    assert len(client.query_ticker("FPT")) == 1

    # 3-char trap fix: "dầu" and "GDP" resolve as keyword, never TICKER:DẦU or TICKER:GDP.
    assert client.resolve_target("dầu")["mode"] == "keyword"
    assert client.resolve_target("GDP")["mode"] == "keyword"
    assert client.resolve_target("HPG")["mode"] == "ticker"

    # Tone/accent-insensitive search matches "Hòa Phát", "Hoà Phát", and "Hoa Phat" identically.
    tl_1 = client.timeline("Hòa Phát", date_from="2026-11-01", date_to="2026-11-11")
    tl_2 = client.timeline("Hoà Phát", date_from="2026-11-01", date_to="2026-11-11")
    tl_3 = client.timeline("Hoa Phat", date_from="2026-11-01", date_to="2026-11-11")
    assert tl_1["stories_total"] == 1
    assert tl_1["stories_total"] == tl_2["stories_total"] == tl_3["stories_total"]

    # key_points search matches "Dung Quất" even when it only appears in key_points.
    tl_kp = client.timeline("Dung Quat", date_from="2026-11-01", date_to="2026-11-11")
    assert tl_kp["stories_total"] == 1

    # SQL security blocks external file-reading functions and pragma/copy without spaces.
    for bad_sql in (
        "SELECT * FROM read_text('secret.txt')",
        "SELECT * FROM read_parquet('other.parquet')",
        "SELECT * FROM glob('*')",
        "PRAGMA database_list",
        "COPY(SELECT 1) TO 'out.csv'",
    ):
        with pytest.raises(ValueError, match="Chỉ cho phép truy vấn đọc dữ liệu"):
            client.query_custom_sql(bad_sql)


def test_priority_refresh_cli_sensor_fast_track_and_fulfillment(tmp_path: Path, monkeypatch) -> None:
    """Verify CLI priority-refresh subprocess, Tier-1 fast-track rules, and wave fulfillment."""
    data_dir = tmp_path / "ops_data"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(data_dir))
    cfg = load_config()
    paths = resolve_paths(data_dir)
    ops_store = OpsStore(paths.ops_db, log_dir=paths.log_dir, dedup_minutes=30)

    # Real subprocess execution of lakehouse_client.py request-refresh (Rule 03 §5.5).
    cli_path = PLUGIN_TOOLS_DIR / "lakehouse_client.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "request-refresh",
            "--target",
            "HPG",
            "--ops-db",
            str(paths.ops_db),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, (proc.stderr or "")
    payload = json.loads(proc.stdout or "{}")
    assert payload["status"] == "queued" and payload["target"] == "HPG"

    # Insert one pending Tier-1 article into isolated monocle.db.
    now = datetime(2026, 11, 12, 10, 30, tzinfo=VN_TZ)
    fetched = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
    art_store = ArticleStore(db_path=data_dir / "monocle.db")
    art_store.insert(Article(
        url="https://cafef.vn/nhnn-dieu-hanh",
        title="NHNN điều hành lãi suất thị trường mở phiên sáng",
        source_domain="cafef.vn",
        content_text=(
            "Ngân hàng Nhà nước vừa thông báo kết quả đấu thầu thị trường mở với lãi suất ổn định.\n"
            "Thanh khoản hệ thống ngân hàng thương mại duy trì trạng thái dồi dào trong tuần qua."
        ),
        fetched_at=fetched,
        published_at=fetched,
    ))

    reading = read_pending(data_dir / "monocle.db", 1, now=now, ops_db=paths.ops_db)
    assert reading.priority_targets == ["HPG"]
    assert reading.tier1_count == 1
    ok_pri, rule_pri, _ = decide(reading, cfg["sensor"], now=now)
    assert ok_pri is True and rule_pri == "T_PRI"

    # Without priority_targets, a 30-minute-old Tier-1 article during trading hours triggers T2_TIER1.
    reading_t1 = SensorReading(
        per_date=[(now.date().isoformat(), 3)],
        oldest_fetched_at=now - timedelta(minutes=30),
        tier1_count=2,
        oldest_tier1_fetched_at=now - timedelta(minutes=30),
    )
    ok_t1, rule_t1, _ = decide(reading_t1, cfg["sensor"], now=now)
    assert ok_t1 is True and rule_t1 == "T2_TIER1"

    # Outside trading hours (21:00), T2_TIER1 does not fire prematurely.
    evening = datetime(2026, 11, 12, 21, 0, tzinfo=VN_TZ)
    reading_eve = SensorReading(
        per_date=[(evening.date().isoformat(), 3)],
        oldest_fetched_at=evening - timedelta(minutes=30),
        tier1_count=2,
        oldest_tier1_fetched_at=evening - timedelta(minutes=30),
    )
    assert decide(reading_eve, cfg["sensor"], now=evening)[0] is False

    # Completing a wave marks pending ops_priority_requests as fulfilled.
    steps = WaveSteps(ops_store, cfg, paths)
    steps._sync_intraday_master(WaveSpec(
        wave_id="W_TEST",
        target_date=now.date().isoformat(),
        trigger="T_PRI",
        level="L1",
    ))
    assert request_priority_refresh is not None
    with sqlite3.connect(paths.ops_db) as c:
        row = c.execute(
            "SELECT status, fulfilled_wave_id FROM ops_priority_requests WHERE target = 'HPG'"
        ).fetchone()
    assert row == ("fulfilled", "W_TEST")
