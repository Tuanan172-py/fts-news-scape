"""Provide a mixin that captures article details and stores Bronze files for scrapers."""

from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from src.crawler.backoff import SourceBackoff
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate

# Markers that identify an error or empty page when downloading content.
_EMPTY_MARKERS = (
    "vui lòng bật javascript", "please enable javascript",
    "checking your browser", "access denied", "captcha",
)


class CaptureMixin:
    """Handle compliance checks, detail capture and DOM subtree extraction for scrapers."""

    def _init_capture(self) -> None:
        """Initialize RawStore, RobotsGate and SourceBackoff from the config."""
        cap_cfg = self.config.get("capture", {}) or {}
        self.raw_store = RawStore(cap_cfg.get("raw_dir"))
        self.min_body_bytes = cap_cfg.get("min_body_bytes", 2048)
        comp = self.config.get("compliance", {}) or {}
        self.respect_robots = comp.get("respect_robots", True)
        self.proxy_rotation = comp.get("proxy_rotation", False)
        self.robots = RobotsGate(self.http) if self.respect_robots else None
        self.backoff = SourceBackoff()
        if self.proxy_rotation and hasattr(self.http, "set_proxy_pool"):
            self.http.set_proxy_pool(comp.get("proxies", []))

    def _capture_and_extract(self, article, domain: str, referer: str,
                             selector: str) -> str | None:
        """Download the detail page, store the raw Bronze artifact and extract the content HTML region.

        Args:
            article: Article to enrich.
            domain: Domain of the news source.
            referer: Referer header sent with the request.
            selector: CSS selector of the main content block.

        Returns:
            Detail page HTML on success, or None on failure.
        """
        url = article.url

        # robots gate (AC9): block before fetching
        if self.respect_robots and self.robots is not None \
                and not self.robots.allowed(url):
            cap = article.metadata.setdefault("capture", {})
            cap["capture_status"] = "skipped_robots"
            article.content_text = article.summary
            self.errors.append(f"robots disallow: {url}")
            return None

        # crawl-delay (when robots declares one): applied only when larger than the default
        if self.robots is not None and hasattr(self.http, "rate_limiter"):
            cd = self.robots.crawl_delay(domain)
            if cd and cd > 0:
                self.http.rate_limiter.wait(url, cd)

        # adaptive backoff pause (D4)
        if self.backoff is not None:
            self.backoff.before_fetch(domain)

        resp = self.http.get_response(url, referer=referer,
                                      timeout=self.config.get("timeout", 30))
        status = getattr(resp, "status_code", None) if resp is not None else None
        if self.backoff is not None:
            self.backoff.observe(domain, status if status is not None else 503)
        if resp is not None and status in (429, 503) and self.proxy_rotation \
                and hasattr(self.http, "rotate_proxy"):
            self.http.rotate_proxy()

        # RawStore.save is the first action after the fetch (byte-exact, no cleaning).
        cap = self.raw_store.save(domain, url, article.url_title_hash, resp,
                                  fetched_at=article.fetched_at)
        article.metadata["capture"] = cap
        if cap.get("capture_status") == "deleted_at_source":
            article.metadata["source_deleted"] = True

        if resp is None or not getattr(resp, "ok", False):
            article.content_text = article.summary
            self.errors.append(f"detail fetch failed: {url}")
            return None

        html = resp.text
        node = None
        try:
            node = BeautifulSoup(html, "lxml").select_one(selector)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("[{}] selector error {}: {}", self.name, selector, e)
        if node is not None and node.get_text(strip=True):
            article.content_html = str(node)  # referenced subtree (primary)
        else:
            # D5 density fallback: changes only content_html; the stored raw .html is untouched.
            article.content_html = self._density_extract(html) or html
            cap.setdefault("missing", []).append("main_content_node")

        # D1 validity check: feeds phase-05 and does not mutate the raw artifact.
        if not self._looks_complete(html, selector):
            cap["capture_status"] = "partial"
            cap.setdefault("missing", []).append("incomplete_render")
        return html

    # -- helpers --------------------------------------------------------------
    def _looks_complete(self, html: str, selector: str) -> bool:
        """Run a preliminary completeness check of a detail page from its size and content.

        Args:
            html: HTML string of the detail page.
            selector: CSS selector of the main content.

        Returns:
            True if the page rendered fully and contains no error markers.
        """
        if not html:
            return False
        if len(html.encode("utf-8", errors="ignore")) < self.min_body_bytes:
            return False
        low = html[:4000].lower()
        if any(m in low for m in _EMPTY_MARKERS):
            return False
        try:
            node = BeautifulSoup(html, "lxml").select_one(selector)
        except Exception:  # pragma: no cover - defensive
            return False
        return node is not None and bool(node.get_text(strip=True))

    def _density_extract(self, html: str) -> str | None:
        """Extract the main content block by text density when the CSS selector has drifted.

        Args:
            html: Article HTML source.

        Returns:
            HTML fragment with the main content, or None when extraction fails.
        """
        if not html:
            return None
        try:
            from readability import Document  # readability-lxml (optional)
            summary = Document(html).summary(html_partial=True)
            if summary and summary.strip():
                return summary
        except ImportError:
            pass
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("readability fallback failed: {}", e)
        try:
            from goose3 import Goose  # optional
            art = Goose().extract(raw_html=html)
            if art.cleaned_text:
                return f"<div>{art.cleaned_text}</div>"
        except ImportError:
            return None
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("goose3 fallback failed: {}", e)
        return None
