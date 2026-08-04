"""
Tests cho Orchestrator — cycle hoàn chỉnh với mock scrapers, config-drift guard.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import src.orchestrator as orch_mod
from src.core.base_scraper import BaseScraper
from src.core.config import list_domains, load_domain_config
from src.core.models import Article
from src.orchestrator import Orchestrator, build_scraper
from src.scrapers import REGISTRY


def test_every_domain_config_resolves_to_scraper_class():
    """Config-drift guard: mọi yaml trong config/domains/ phải build được."""
    names = list_domains(enabled_only=False)
    assert len(names) >= 5  # cafef, tnck, fireant, vietstock, vnexpress, baodautu, vneconomy
    for name in names:
        cfg = load_domain_config(name)
        cls = REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")
        assert cls is not None, f"{name}: no scraper class for method={cfg['method']}"
        assert issubclass(cls, BaseScraper)


class OkScraper(BaseScraper):
    def fetch_list(self):
        return [{"url": "https://ok.com/1", "title": "Cổ phiếu HPG tăng trần phiên sáng"}]

    def parse_item(self, raw):
        return Article(url=raw["url"], title=raw["title"], source_domain="ok.com",
                       summary="tóm tắt", content_text="HPG tăng trần với thanh khoản cao")


class BoomScraper(BaseScraper):
    def fetch_list(self):
        raise RuntimeError("source is down")

    def parse_item(self, raw):  # pragma: no cover
        return None


@pytest.fixture
def orch(tmp_path, monkeypatch):
    monkeypatch.setattr(orch_mod, "load_settings", lambda: {
        "database": {"path": str(tmp_path / "t.db")},
        "logging": {"level": "INFO", "dir": str(tmp_path / "logs")},
        "scheduler": {"interval_minutes": 15},
        "http": {"rate_limit": 0.0, "timeout": 5, "max_retries": 1},
        "notifications": {"dir": str(tmp_path / "notif")},  # cô lập, không ghi log thật
        "export": {"enabled": True, "dir": str(tmp_path / "exports")},  # cô lập CSV
    })
    configs = {
        "okdomain": {"name": "okdomain", "method": "api", "enabled": True,
                     "fuzzy_dedup": False},
        "boomdomain": {"name": "boomdomain", "method": "api", "enabled": True},
        "offdomain": {"name": "offdomain", "method": "api", "enabled": False},
    }
    monkeypatch.setattr(orch_mod, "list_domains",
                        lambda enabled_only=True: list(configs))
    monkeypatch.setattr(orch_mod, "load_domain_config", lambda n: configs[n])
    monkeypatch.setitem(REGISTRY, "okdomain", OkScraper)
    monkeypatch.setitem(REGISTRY, "boomdomain", BoomScraper)
    monkeypatch.setitem(REGISTRY, "offdomain", OkScraper)
    # retry không chờ backoff trong test
    import src.core.retry as retry_mod
    monkeypatch.setattr(retry_mod._attempt.retry, "wait", lambda *a, **k: 0)

    o = Orchestrator()
    yield o
    o.shutdown()


def test_cycle_mixed_success_failure(orch):
    new_count = orch.run_cycle()
    assert new_count == 1  # okdomain 1 bài; boomdomain fail; offdomain skip

    # Article được ghi DB với sentiment + classify
    articles = orch.store.get_recent(limit=10)
    assert len(articles) == 1
    a = articles[0]
    assert a.sentiment == "positive"          # "tăng trần"
    assert "finance" in a.categories          # classifier wired

    # Heartbeat: ok + failed, disabled không có record
    conn = orch.store._connect()
    rows = {r["scraper_name"]: r for r in
            conn.execute("SELECT * FROM scraper_heartbeat").fetchall()}
    conn.close()
    assert rows["okdomain"]["status"] == "ok"
    assert rows["boomdomain"]["status"] == "failed"
    assert rows["boomdomain"]["consecutive_failures"] >= 1


def test_cycle_auto_exports_csv(orch, tmp_path):
    """Cuối cycle: flush writer + tự xuất CSV 'hôm nay' chứa bài vừa thu."""
    import csv as _csv

    orch.run_cycle()
    exports = list((tmp_path / "exports").glob("articles-*.csv"))
    assert len(exports) == 1                      # đúng 1 file CSV hôm nay
    with exports[0].open(encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    # flush đảm bảo bài cycle này đã commit → có mặt trong CSV
    assert any("HPG" in r["title"] for r in rows)
    assert rows[0]["source_domain"] == "ok.com"
    assert rows[0]["sentiment"] == "positive"
    assert "offdomain" not in rows


def test_second_cycle_dedups(orch):
    assert orch.run_cycle() == 1
    assert orch.run_cycle() == 0  # dedup


def test_build_scraper_unknown_method_raises():
    with pytest.raises(KeyError):
        build_scraper({"name": "zzz", "method": "carrier-pigeon"}, None, None)
