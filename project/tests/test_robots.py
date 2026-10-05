"""
Tests RobotsGate — allow/deny, crawl-delay, fail-open khi robots outage.
"""

from _fakes import FakeHTTP
from src.crawler.robots import RobotsGate

ROBOTS = """User-agent: *
Disallow: /private/
Crawl-delay: 5
"""


def test_allow_and_deny():
    gate = RobotsGate(FakeHTTP(robots_txt=ROBOTS))
    assert gate.allowed("https://x.vn/public/a.htm") is True
    assert gate.allowed("https://x.vn/private/secret.htm") is False


def test_crawl_delay_parsed():
    gate = RobotsGate(FakeHTTP(robots_txt=ROBOTS))
    assert gate.crawl_delay("x.vn") == 5.0


def test_fail_open_on_outage():
    # robots_txt=None → http.get trả None → fail-open (allow) + crawl_delay None
    gate = RobotsGate(FakeHTTP(robots_txt=None))
    assert gate.allowed("https://x.vn/anything") is True
    assert gate.crawl_delay("x.vn") is None


def test_cache_single_fetch(monkeypatch):
    http = FakeHTTP(robots_txt=ROBOTS)
    calls = {"n": 0}
    orig = http.get

    def counting_get(url, **kw):
        if "robots.txt" in url:
            calls["n"] += 1
        return orig(url, **kw)

    monkeypatch.setattr(http, "get", counting_get)
    gate = RobotsGate(http)
    gate.allowed("https://x.vn/a")
    gate.allowed("https://x.vn/b")
    gate.crawl_delay("x.vn")
    assert calls["n"] == 1  # cache per-domain
