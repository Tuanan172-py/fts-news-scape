"""
Tests _looks_complete (D1) + _density_extract (D5) trên CaptureMixin.
"""

from src.scrapers.capture_mixin import CaptureMixin

SELECTOR = "div#mainContent"


class _M(CaptureMixin):
    def __init__(self, min_body_bytes=2048):
        self.min_body_bytes = min_body_bytes
        self.name = "t"


def _full_page():
    filler = "<p>Nội dung bài viết rất dài. </p>" * 100  # > 2KB
    return f'<html><body><div id="mainContent">{filler}</div></body></html>'


def test_complete_page_true():
    assert _M()._looks_complete(_full_page(), SELECTOR) is True


def test_short_body_false():
    html = '<html><body><div id="mainContent">ngắn</div></body></html>'
    assert _M()._looks_complete(html, SELECTOR) is False


def test_missing_container_false():
    big = "<p>x</p>" * 500
    html = f"<html><body><article>{big}</article></body></html>"  # no #mainContent
    assert _M()._looks_complete(html, SELECTOR) is False


def test_empty_render_marker_false():
    html = ('<html><body><div id="mainContent">'
            + "Vui lòng bật JavaScript để xem. " * 100
            + '</div></body></html>')
    assert _M()._looks_complete(html, SELECTOR) is False


def test_density_extract_graceful_without_lib():
    # readability/goose3 không cài trong base → trả None, không crash
    out = _M()._density_extract("<html><body><p>abc</p></body></html>")
    assert out is None or isinstance(out, str)
