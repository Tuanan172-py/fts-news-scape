"""
Báo Đầu Tư scraper — HTML listing cho list, capture full raw HTML cho detail.

RSS VĨNH VIỄN HỎNG (verified 2026-09-07, 8/8 URL): mọi feed trả CÙNG một channel
rỗng `<title>Trang chủ</title><link>https://baodautu.vn//.rss</link>` (double-slash,
không có category) với 0 <item> → generator phía server hỏng, KHÔNG phải "dormant".
`rssMain.html` trả HTML homepage 34KB, không phải feed. Đừng probe lại, đừng chờ.

Đây là nguồn HTML-listing ĐẦU TIÊN của repo — ngoại lệ có chủ ý của TDR-001
(RSS > API > HTML): baodautu không có cả RSS lẫn API, nhưng là nguồn số 1 về
giải ngân đầu tư công / FDI / hạ tầng nên không thể bỏ.

List: trang 1 = `{base}/{slug}-d{id}/` (CÓ dấu / cuối)
      trang N = `{base}/{slug}-d{id}/p{N}`  (⚠️ THÊM / cuối → 404)
      ⚠️ item KHÔNG phải `div.thumbblock` — class `thumbblock` nằm trên thẻ <a> ẢNH
      (select("div.thumbblock") trả 0 node dù chuỗi xuất hiện 35 lần). Item thật là
      thẻ <article>; trong đó link ảnh (KHÔNG có text) đứng TRƯỚC link tiêu đề nên
      select_one() sẽ vớ phải link ảnh → mất sạch bài. Phải duyệt hết anchor và lấy
      cái đầu tiên vừa có text vừa khớp link_pattern.
      KHÔNG có ngày đăng trên listing → published_at điền ở enrich() từ trang detail.

Detail: body = #content_detail_news
  ⚠️ TUYỆT ĐỐI KHÔNG dùng selector `.content` — trong source có chuỗi template JS
     `<div class="content">'+content+'</div>'` của widget bình luận, selector ngây thơ
     sẽ bắt nhầm node đó.
  Trang KHÔNG có <h1>; title lấy từ listing, đối chiếu div.title-detail.
  Ngày = text thuần `dd/MM/yyyy HH:mm` trong span.post-time (nằm NGOÀI body).
  KHÔNG có <time>, KHÔNG có article:published_time, KHÔNG có JSON-LD.
  Paragraph mã hoá HTML entity (&ecirc;).
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import VN_TZ, Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin

BASE_URL = "https://baodautu.vn"
SOURCE_DOMAIN = "baodautu.vn"
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")


def _parse_detail_date(html: str, scope_selector: str) -> str:
    """`dd/MM/yyyy HH:mm` (text thuần) → ISO +07:00. Rỗng nếu không khớp — KHÔNG bịa.

    baodautu KHÔNG có <time> / article:published_time / JSON-LD (verified 2026-09-07).
    Ngày nằm ở span.post-time, NGOÀI #content_detail_news → thu hẹp scope để không
    khớp nhầm một ngày nào đó nằm trong thân bài.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(scope_selector) or soup
        m = _DATE_RE.search(node.get_text(" ", strip=True))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[baodautu] date parse failed: {}", e)
        return ""
    if not m:
        return ""
    d, mo, y, hh, mm = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, hh, mm, tzinfo=VN_TZ).isoformat(timespec="seconds")
    except ValueError:
        return ""


@register("baodautu")
class BaodautuScraper(CaptureMixin, BaseScraper):
    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        listing = config.get("listing", {}) or {}
        self.categories = listing.get("categories", [])
        self.pages_per_cycle = listing.get("pages_per_cycle", 1)
        self.item_selector = listing.get("item_selector", "article")
        self.link_selector = listing.get("link_selector", "a[href]")
        self.sapo_selector = listing.get(
            "sapo_selector", "div.sapo_thumb_news, div.desc_list_news_home")
        self.link_pattern = re.compile(
            listing.get("link_pattern", r"-d\d+\.html"))
        detail = config.get("detail", {}) or {}
        self.content_selector = detail.get("content_selector", "#content_detail_news")
        self.date_scope = detail.get("date_scope_selector", "span.post-time")
        self.author_selector = detail.get("author_selector", "a.author")
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.base_url = (config.get("base_url") or BASE_URL).rstrip("/")
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()

    # -- listing ------------------------------------------------------------
    def _page_url(self, slug: str, cid, page: int) -> str:
        """Trang 1 = `…-d<N>/` (CÓ /). Trang >1 = `…-d<N>/p<page>` (KHÔNG / cuối → 404)."""
        return (f"{self.base_url}/{slug}-d{cid}/" if page == 1
                else f"{self.base_url}/{slug}-d{cid}/p{page}")

    def _parse_listing(self, html: str, cat: dict, listing_url: str) -> list[dict]:
        out: list[dict] = []
        try:
            blocks = BeautifulSoup(html, "lxml").select(self.item_selector)
        except Exception as e:  # pragma: no cover - defensive
            self.errors.append(f"listing parse error {listing_url}: {e}")
            return out
        for b in blocks:
            # Mỗi <article> có NHIỀU <a>: link ảnh (a.thumbblock — KHÔNG có text) đứng
            # TRƯỚC link tiêu đề. select_one() sẽ vớ phải link ảnh rồi bị bỏ qua →
            # mất bài. Vì vậy duyệt hết và lấy anchor ĐẦU TIÊN vừa có text vừa khớp
            # link_pattern của bài viết.
            href = title = ""
            for a in b.select(self.link_selector):
                cand_href = (a.get("href") or "").strip()
                cand_title = a.get_text(" ", strip=True)
                if cand_href and cand_title and self.link_pattern.search(cand_href):
                    href, title = cand_href, cand_title
                    break
            if not href or not title:
                continue
            sapo_node = b.select_one(self.sapo_selector)
            out.append({
                "link": href,
                "title": title,
                "sapo": sapo_node.get_text(" ", strip=True) if sapo_node else "",
                "_cat_name": cat.get("name", ""),
                "_listing_url": listing_url,
            })
        return out

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for cat in self.categories:
            for page in range(1, self.pages_per_cycle + 1):
                url = self._page_url(cat["slug"], cat["id"], page)
                html = self.http.get(url, referer=f"{self.base_url}/",
                                     timeout=self.config.get("timeout", 30))
                if html is None:
                    self.errors.append(f"listing fetch failed: {url}")
                    continue                       # category isolation
                found = self._parse_listing(html, cat, url)
                if not found:
                    self.errors.append(f"listing 0 items (template drift?): {url}")
                items.extend(found)
        return items

    def parse_item(self, raw: dict) -> Article | None:
        url = (raw.get("link") or "").strip()
        title = (raw.get("title") or "").strip()
        if not url or not title:
            return None
        summary = (raw.get("sapo") or "").strip()
        cat = raw.get("_cat_name") or ""
        return Article(
            url=urljoin(self.base_url + "/", url),
            title=title,
            source_domain=SOURCE_DOMAIN,
            summary=summary,
            published_at="",                       # detail-only — điền ở enrich()
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[cat] if cat else [],
            metadata={"language": self.language,
                      "listing_url": raw.get("_listing_url", "")},
        )

    # -- detail -------------------------------------------------------------
    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, SOURCE_DOMAIN,
                                         f"{self.base_url}/", self.content_selector)
        if html is None:
            return                                 # mixin đã set summary + errors
        self._details_fetched += 1

        article.published_at = _parse_detail_date(html, self.date_scope)
        if not article.published_at:
            # KHÔNG bịa timestamp — ghi nhận là thiếu để drift report nhìn thấy
            article.metadata.setdefault("capture", {}) \
                .setdefault("missing", []).append("published_at")

        if self.author_selector:
            try:
                node = BeautifulSoup(html, "lxml").select_one(self.author_selector)
                if node is not None:
                    article.author = node.get_text(" ", strip=True)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("[baodautu] author parse failed: {}", e)

        article.content_text = extract_text(article.content_html) or article.summary
