"""
FireAnt scraper — REST API (Bearer token), 2-step fetch + Bronze capture JSON.

List:   GET https://restv2.fireant.vn/posts?symbol={S}&type=1&offset=0&limit=20
Detail: GET https://restv2.fireant.vn/posts/{post_id}   (SỐ NHIỀU — /post/{id} → 404)

⚠️ BRONZE CỦA NGUỒN NÀY LÀ **JSON**, KHÔNG PHẢI HTML
Trang web `fireant.vn/dashboard/content/{id}` là Next.js SPA (`__NEXT_DATA__`), body bài
KHÔNG có trong HTTP GET → capture trang web là vô nghĩa. Nguồn sự thật duy nhất là
response JSON của API detail, trong đó `content` là HTML thân bài.
→ `enrich()` gọi thẳng `RawStore.save()` trên response detail (byte-exact), KHÔNG dùng
`CaptureMixin._capture_and_extract` (hàm đó giả định body là HTML: `_looks_complete`
chạy CSS selector nên sẽ báo `partial` oan cho mọi bài).
→ `SilverBuilder` nhận diện `Content-Type: application/json` và tự bóc trường HTML
(nhánh generic theo ĐỊNH DẠNG, xem `_html_from_json`).

Verified 2026-09-07:
- Token trong `config/secrets.yaml` còn hạn (JWT exp 2036); list + detail đều HTTP 200.
- List trả `content` RỖNG → bắt buộc gọi detail (`content` ~3.7k HTML).
- Field thật là `postID`/`postSource`/`postSourceUrl` (camelCase). Bản cũ đọc
  `post_source` (snake_case) nên `source_name`/`source_url` LUÔN rỗng — đã sửa.
- Permalink đúng là `/dashboard/content/{id}`; `/bai-viet/{id}` trả **404** — đã sửa.
- `date` đã ISO +07:00 sẵn.
- Ảnh trên `static.fireant.vn`.

⚠️ TUÂN THỦ — xem `domains/fireant/README.md` trước khi mở rộng:
robots.txt của **fireant.vn** chặn tường minh ClaudeBot/GPTBot/CCBot/Google-Extended… và
khai `Content-Signal: search=yes, ai-train=no, use=reference`. Ta đi qua **API đã xác thực
bằng token của chính người dùng** (`restv2.fireant.vn`, không có robots.txt), tức chịu ràng
buộc của ToS tài khoản chứ không phải robots dành cho crawler ẩn danh. KHÔNG dùng dữ liệu
này để huấn luyện model (`ai-train=no`).
"""

from __future__ import annotations

import json

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_secrets, load_watchlist
from src.core.models import Article, now_vn_iso
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin


@register("fireant")
class FireAntScraper(CaptureMixin, BaseScraper):
    LIST_URL = "https://restv2.fireant.vn/posts"
    DETAIL_URL = "https://restv2.fireant.vn/posts/{post_id}"   # số nhiều
    WEB_URL = "https://fireant.vn/dashboard/content/{post_id}"  # /bai-viet/ → 404
    SOURCE_DOMAIN = "fireant.vn"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.list_url = api.get("list_url", self.LIST_URL)
        self.detail_url = api.get("detail_url_template", self.DETAIL_URL)
        self.list_params = api.get("params", {"type": 1, "offset": 0, "limit": 20})
        detail = config.get("detail", {})
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()          # RawStore + RobotsGate + SourceBackoff

        token = (config.get("_secrets") or load_secrets()).get("fireant_token", "").strip()
        if token[:7].lower() == "bearer ":   # user dán kèm "Bearer " → strip cho khỏi nhân đôi
            token = token[7:].strip()
        if not token or token.startswith("PASTE_"):
            logger.warning("[fireant] no token in config/secrets.yaml — scraper disabled")
            self.disabled = True
            token = ""
        self.auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # -- helpers --------------------------------------------------------------
    def _api_headers(self) -> dict:
        return {**self.auth_headers, "Accept": "application/json, text/plain, */*"}

    def _auth_failed(self, status: int, context: str) -> None:
        """401/403 → disable phần còn lại của cycle, không hammer API."""
        self.disabled = True
        msg = (f"auth failed (HTTP {status}) at {context} — token expired? "
               f"Update config/secrets.yaml fireant_token")
        logger.error("[fireant] {}", msg)
        self.errors.append(msg)

    # -- pipeline -------------------------------------------------------------
    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for sym in self.watchlist:
            if self.disabled:
                break
            resp = self.http.get_response(
                self.list_url,
                params={**self.list_params, "symbol": sym},
                headers=self._api_headers(),
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
        post_id = raw.get("postID") or raw.get("post_id")
        title = (raw.get("title") or "").strip()
        if not post_id or not title:
            logger.warning("[fireant] item missing postID/title, skipped")
            return None
        symbols = []
        for s in raw.get("taggedSymbols") or []:
            sym = (s.get("symbol") or "").upper() if isinstance(s, dict) else str(s).upper()
            if sym and sym not in symbols:
                symbols.append(sym)
        # field thật là camelCase (bản cũ đọc snake_case → luôn rỗng)
        source = raw.get("postSource") or raw.get("post_source") or {}
        if not isinstance(source, dict):
            source = {}
        return Article(
            url=self.WEB_URL.format(post_id=post_id),
            title=title,
            source_domain=self.SOURCE_DOMAIN,
            summary=(raw.get("description") or "").strip(),
            published_at=(raw.get("date") or "").strip(),   # đã ISO +07:00
            symbols=symbols,
            metadata={"post_id": post_id,
                      "source_name": source.get("name", "") or "",
                      "source_url": (source.get("url", "")
                                     or raw.get("postSourceUrl", "") or ""),
                      "language": self.language},
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
        if self.backoff is not None:
            self.backoff.before_fetch(self.SOURCE_DOMAIN)
        resp = self.http.get_response(url, headers=self._api_headers(),
                                      timeout=self.config.get("timeout", 30))
        status = getattr(resp, "status_code", None) if resp is not None else None
        if self.backoff is not None:
            self.backoff.observe(self.SOURCE_DOMAIN, status if status is not None else 503)

        if status in (401, 403):
            # KHÔNG ghi Bronze cho response lỗi auth — nó không phải nội dung bài
            self._auth_failed(status, f"detail {article.metadata['post_id']}")
            article.content_text = article.summary
            return

        # ★ Bronze TRƯỚC mọi parse — byte-exact body JSON (design 06 §2, AC7)
        cap = self.raw_store.save(self.SOURCE_DOMAIN, url, article.url_title_hash,
                                  resp, fetched_at=article.fetched_at)
        article.metadata["capture"] = cap

        if resp is None or status != 200:
            article.content_text = article.summary
            self.errors.append(f"detail fetch failed: {url}"
                               if resp is None
                               else f"detail {article.metadata['post_id']}: HTTP {status}")
            return

        self._details_fetched += 1
        try:
            post = json.loads(resp.content.decode(resp.encoding or "utf-8",
                                                  errors="replace"))
        except (ValueError, AttributeError):
            article.content_text = article.summary
            cap.setdefault("missing", []).append("article_body")
            cap["capture_status"] = "partial"
            self.errors.append(f"detail invalid JSON: {url}")
            return

        content_html = post.get("content") or post.get("originalContent") or ""
        if not content_html:
            cap.setdefault("missing", []).append("article_body")
            cap["capture_status"] = "partial"
        article.content_html = content_html
        article.content_text = (extract_text(content_html)
                                or article.summary
                                or (post.get("description") or ""))
