"""
Tests cho Heartbeat + health check + FileNotifier + retry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.models import Article, ScrapeResult
from src.core.retry import run_with_fallback, run_with_retry
from src.db.store import ArticleStore
from src.monitor.health import check
from src.monitor.heartbeat import Heartbeat
from src.notifier.file_notify import FileNotifier


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "t.db"))


def _result(name="dummy", fetched=5, new_count=2, errors=None):
    new = [Article(url=f"https://x.com/{i}", title=f"Tin HPG số {i}",
                   source_domain="x.com", sentiment="positive")
           for i in range(new_count)]
    return ScrapeResult(scraper=name, fetched=fetched, new=new,
                        errors=errors or [], duration_s=1.5)


# ---- heartbeat + health ------------------------------------------------------

def test_heartbeat_ok_cycle(store):
    hb = Heartbeat(store)
    hb.record_start("cafef")
    hb.record_result(_result("cafef"))
    report, all_ok = check(store)
    assert all_ok
    row = report[0]
    assert row["scraper"] == "cafef" and row["state"] == "OK"
    assert row["cycles"] == 1 and row["consec_fails"] == 0


def test_heartbeat_consecutive_failures_critical(store):
    hb = Heartbeat(store)
    for _ in range(3):
        hb.record_start("tnck")
        hb.record_result(_result("tnck", fetched=0, new_count=0,
                                 errors=["network down"]))
    report, all_ok = check(store)
    assert not all_ok
    assert report[0]["state"] == "CRITICAL"
    assert report[0]["consec_fails"] == 3


def test_heartbeat_failure_reset_on_success(store):
    hb = Heartbeat(store)
    hb.record_result(_result("cafef", fetched=0, new_count=0, errors=["x"]))
    hb.record_result(_result("cafef"))
    report, all_ok = check(store)
    assert all_ok and report[0]["consec_fails"] == 0


# ---- notifier ----------------------------------------------------------------

def _notifier(tmp_path, rules_yaml):
    cfg = tmp_path / "notifications.yaml"
    cfg.write_text(rules_yaml, encoding="utf-8")
    return FileNotifier(config_path=str(cfg), out_dir=str(tmp_path / "notif"))


def test_notify_keyword_match_writes_log(tmp_path, capsys):
    n = _notifier(tmp_path, 'rules:\n  - tag: "wl"\n    match:\n      any: ["HPG"]\n')
    count = n.notify_articles(_result().new)
    assert count == 2  # cả 2 title chứa HPG
    logs = list((tmp_path / "notif").glob("*.log"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    # format tối giản: <emoji> <title> (chi tiết (<url>))
    assert "🟢 Tin HPG số 0 (chi tiết (https://x.com/0))" in content
    assert content.count("🟢") == 2


def test_notify_sentiment_emoji_mapping(tmp_path):
    from src.core.models import Article
    n = _notifier(tmp_path, "rules: []\n")
    cases = [("positive", "🟢"), ("negative", "🔴"), ("neutral", "🟡"), ("", "🟡")]
    for sentiment, emoji in cases:
        a = Article(url="https://x.com/1", title="Tiêu đề", source_domain="x.com",
                    sentiment=sentiment)
        line = n.format_article(a, tag="wl")
        assert line == f"{emoji} Tiêu đề (chi tiết (https://x.com/1))"


def test_notify_no_match_no_log(tmp_path):
    n = _notifier(tmp_path, 'rules:\n  - tag: "wl"\n    match:\n      any: ["XYZ999"]\n')
    assert n.notify_articles(_result().new) == 0
    assert not list((tmp_path / "notif").glob("*.log"))


def test_notify_has_symbol_rule(tmp_path):
    """has_symbol: khớp bài có gắn mã bất kỳ (kể cả ngoài watchlist)."""
    from src.core.models import Article
    n = _notifier(tmp_path, 'rules:\n  - tag: "symbol"\n    has_symbol: true\n')
    off_wl = Article(url="https://x.com/1", title="Tin không keyword nào",
                     source_domain="x.com", symbols=["HND"])  # mã ngoài watchlist
    no_sym = Article(url="https://x.com/2", title="Tin thường không mã",
                     source_domain="x.com")
    assert n._matches(off_wl) == "symbol"
    assert n._matches(no_sym) is None


def test_notify_sources_rule(tmp_path):
    """sources: khớp mọi bài từ nguồn tài chính, kể cả tiêu đề tiếng Anh không keyword VN."""
    from src.core.models import Article
    n = _notifier(tmp_path,
                  'rules:\n  - tag: "finance"\n    sources: ["cnbc.com"]\n')
    en = Article(url="https://cnbc.com/a", title="Stocks rally on earnings",
                 source_domain="cnbc.com")
    other = Article(url="https://x.com/b", title="Stocks rally on earnings",
                    source_domain="x.com")
    assert n._matches(en) == "finance"
    assert n._matches(other) is None


def test_cycle_summary_includes_failures(tmp_path, capsys):
    n = _notifier(tmp_path, "rules: []\n")
    n.notify_cycle_summary([_result("cafef"),
                            _result("tnck", fetched=0, new_count=0,
                                    errors=["endpoint dead"])])
    out = capsys.readouterr().out
    assert "cafef: 2 new" in out
    assert "tnck: FAILED" in out


# ---- retry / fallback --------------------------------------------------------

class FakeScraper:
    def __init__(self, name, results):
        self.name = name
        self.disabled = False
        self._results = list(results)
        self.calls = 0

    def run(self):
        self.calls += 1
        return self._results.pop(0)


def test_retry_recovers_on_second_attempt(monkeypatch):
    import src.core.retry as retry_mod
    monkeypatch.setattr(retry_mod._attempt.retry, "wait", lambda *a, **k: 0)
    fail = ScrapeResult(scraper="s", fetched=0, errors=["boom"])
    ok = _result("s")
    scraper = FakeScraper("s", [fail, ok])
    result = run_with_retry(scraper)
    assert scraper.calls == 2
    assert result.fetched == 5


def test_retry_exhausted_returns_failed_result(monkeypatch):
    import src.core.retry as retry_mod
    monkeypatch.setattr(retry_mod._attempt.retry, "wait", lambda *a, **k: 0)
    fail = ScrapeResult(scraper="s", fetched=0, errors=["boom"])
    scraper = FakeScraper("s", [fail, fail, fail])
    result = run_with_retry(scraper)
    assert scraper.calls == 3
    assert result.fetched == 0 and result.errors


def test_fallback_used_after_primary_exhausted(monkeypatch):
    import src.core.retry as retry_mod
    monkeypatch.setattr(retry_mod._attempt.retry, "wait", lambda *a, **k: 0)
    fail = ScrapeResult(scraper="p", fetched=0, errors=["dead"])
    primary = FakeScraper("p", [fail, fail, fail])
    fallback = FakeScraper("f", [_result("f")])
    result = run_with_fallback(primary, fallback)
    assert primary.calls == 3 and fallback.calls == 1
    assert result.scraper == "f" and result.fetched == 5
    assert any("dead" in e for e in result.errors)  # lỗi primary được giữ


def test_disabled_scraper_not_retried(monkeypatch):
    import src.core.retry as retry_mod
    monkeypatch.setattr(retry_mod._attempt.retry, "wait", lambda *a, **k: 0)
    fail = ScrapeResult(scraper="fa", fetched=0, errors=["401 token expired"])
    scraper = FakeScraper("fa", [fail])
    scraper.disabled = True  # vd FireAnt 401 self-disable
    result = run_with_retry(scraper)
    assert scraper.calls == 1  # permanent — không retry
