"""
FireAnt scraper — REST API, Bearer token bắt buộc, 2-step fetch.

List:   GET https://restv2.fireant.vn/posts?symbol={S}&type=1&offset=0&limit=20
Detail: GET https://restv2.fireant.vn/post/{post_id}  (field `content` = HTML)
Verified 2026-07-24: không token → 401 "Authorization has been denied".
Token hết hạn → self-disable trong cycle + ERROR log; cập nhật thủ công
config/secrets.yaml (quyết định #1, Phase 1).
"""

from __future__ import annotations

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_secrets, load_watchlist
from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register


@register("fireant")
class FireAntScraper(BaseScraper):
    LIST_URL = "https://restv2.fireant.vn/posts"
    DETAIL_URL = "https://restv2.fireant.vn/posts/{post_id}"  # số nhiều: /post/{id} → 404
    WEB_URL = "https://fireant.vn/bai-viet/{post_id}"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.list_url = api.get("list_url", self.LIST_URL)
        self.detail_url = api.get("detail_url_template", self.DETAIL_URL)
        self.list_params = api.get("params", {"type": 1, "offset": 0, "limit": 20})
        detail = config.get("detail", {})
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self._details_fetched = 0

        token = (config.get("_secrets") or load_secrets()).get("fireant_token", "").strip()
        if token[:7].lower() == "bearer ":   # user dán kèm "Bearer " → strip cho khỏi nhân đôi
            token = token[7:].strip()
        if not token or token.startswith("PASTE_"):
            logger.warning("[fireant] no token in config/secrets.yaml — scraper disabled")
            self.disabled = True
            token = ""
        self.auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _auth_failed(self, status: int, context: str) -> None:
        """401/403 → disable cho phần còn lại của cycle, không hammer API."""
        self.disabled = True
        msg = (f"auth failed (HTTP {status}) at {context} — token expired? "
               f"Update config/secrets.yaml fireant_token")
        logger.error("[fireant] {}", msg)
        self.errors.append(msg)

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for sym in self.watchlist:
            if self.disabled:
                break
            resp = self.http.get_response(
                self.list_url,
                params={**self.list_params, "symbol": sym},
                headers={**self.auth_headers,
                         "Accept": "application/json, text/plain, */*"},
                timeout=self.config.get("timeout", 30),
            )
            if resp is None:
                self.errors.append(f"list fetch failed for {sym}")
                continue
            if resp.status_code in (401, 403):
                self._auth_failed(resp.status_code, f"list {sym}")
                break
            if resp.status_code != 200:
                self.errors.append(f"list {sym}: HTTP {resp.status_code}")
                continue
            try:
                posts = resp.json()
            except ValueError:
                self.errors.append(f"list {sym}: invalid JSON")
                continue
            if isinstance(posts, list):
                items.extend(posts)
        return items

    def parse_item(self, raw: dict) -> Article | None:
        post_id = raw.get("post_id") or raw.get("postID")
        title = (raw.get("title") or "").strip()
        if not post_id or not title:
            logger.warning("[fireant] item missing post_id/title, skipped")
            return None
        symbols = []
        for s in raw.get("taggedSymbols") or []:
            sym = (s.get("symbol") or "").upper() if isinstance(s, dict) else str(s).upper()
            if sym and sym not in symbols:
                symbols.append(sym)
        source = raw.get("post_source") or {}
        return Article(
            url=self.WEB_URL.format(post_id=post_id),
            title=title,
            source_domain="fireant.vn",
            summary=(raw.get("description") or "").strip(),
            published_at=(raw.get("date") or "").strip(),  # đã ISO +07:00
            symbols=symbols,
            metadata={"post_id": post_id,
                      "source_name": source.get("name", ""),
                      "source_url": source.get("url", "")},
        )

    def enrich(self, article: Article) -> None:
        if self.disabled:
            article.content_text = article.summary
            return
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        url = self.detail_url.format(post_id=article.metadata["post_id"])
        resp = self.http.get_response(
            url, headers={**self.auth_headers,
                          "Accept": "application/json, text/plain, */*"},
            timeout=self.config.get("timeout", 30))
        if resp is None:
            article.content_text = article.summary
            self.errors.append(f"detail fetch failed: {url}")
            return
        if resp.status_code in (401, 403):
            self._auth_failed(resp.status_code, f"detail {article.metadata['post_id']}")
            article.content_text = article.summary
            return
        if resp.status_code != 200:   # 404 v.v. → không nuốt im lặng, không phí budget
            article.content_text = article.summary
            self.errors.append(f"detail {article.metadata['post_id']}: HTTP {resp.status_code}")
            return
        self._details_fetched += 1
        try:
            post = resp.json()
        except ValueError:
            article.content_text = article.summary
            self.errors.append(f"detail invalid JSON: {url}")
            return
        content_html = post.get("content") or post.get("original_content") or ""
        article.content_html = content_html
        article.content_text = (extract_text(content_html)
                                or article.summary
                                or (post.get("description") or ""))
