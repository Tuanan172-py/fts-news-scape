"""
Fakes dùng chung cho test capture — không chạm mạng thật.

FakeResponse mô phỏng requests.Response (status_code/ok/content/text/headers/encoding).
FakeHTTP mô phỏng HTTPClient: get_json (list API), get (robots.txt / legacy text),
get_bytes (RSS feed), get_response (detail capture — đếm detail_calls).
"""

from __future__ import annotations


class FakeResponse:
    def __init__(self, text="", status=200, headers=None, encoding="utf-8"):
        if isinstance(text, bytes):
            self.content = text
            self.text = text.decode(encoding, errors="replace")
        else:
            self.text = text
            self.content = text.encode(encoding)
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.encoding = encoding


class FakeHTTP:
    def __init__(self, list_json=None, detail_html=None, detail_status=200,
                 robots_txt="", feed_bytes=None, detail_headers=None):
        self.list_json = list_json
        self.detail_html = detail_html
        self.detail_status = detail_status
        self.robots_txt = robots_txt
        self.feed_bytes = feed_bytes
        self.detail_headers = detail_headers
        self.detail_calls = 0
        self.rotated = 0
        self.proxy_pool: list[str] = []

    def get_json(self, url, **kw):
        return self.list_json

    def get(self, url, **kw):
        if "robots.txt" in url:
            return self.robots_txt
        return self.detail_html

    def get_bytes(self, url, **kw):
        return self.feed_bytes

    def get_response(self, url, **kw):
        self.detail_calls += 1
        if self.detail_html is None and self.detail_status < 400:
            return None  # fetch fail
        return FakeResponse(self.detail_html or "", status=self.detail_status,
                            headers=self.detail_headers)

    # optional proxy hooks (D4)
    def rotate_proxy(self):
        self.rotated += 1

    def set_proxy_pool(self, proxies):
        self.proxy_pool = list(proxies or [])
