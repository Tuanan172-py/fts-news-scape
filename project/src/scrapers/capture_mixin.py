"""Lớp Mixin cung cấp quy trình thu thập nội dung chi tiết và lưu trữ Bronze cho các scraper."""

from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from src.crawler.backoff import SourceBackoff
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate

# Dấu hiệu nhận diện trang bị lỗi hoặc rỗng khi tải nội dung.
_EMPTY_MARKERS = (
    "vui lòng bật javascript", "please enable javascript",
    "checking your browser", "access denied", "captcha",
)


class CaptureMixin:
    """Mixin xử lý kiểm tra tuân thủ, thu thập nội dung chi tiết và bóc tách cây DOM."""

    def _init_capture(self) -> None:
        """Khởi tạo các thành phần RawStore, RobotsGate và SourceBackoff từ cấu hình."""
        cap_cfg = self.config.get("capture", {}) or {}
        self.raw_store = RawStore(cap_cfg.get("raw_dir", "data/raw_html"))
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
        """Tải trang chi tiết, lưu trữ tạo tác thô Bronze và bóc tách vùng HTML nội dung.

        Args:
            article: Đối tượng Article cần bổ sung dữ liệu.
            domain: Tên miền của nguồn tin.
            referer: Header Referer gửi kèm yêu cầu.
            selector: Bộ chọn CSS trỏ tới khối nội dung chính.

        Returns:
            Chuỗi HTML trang chi tiết nếu thành công hoặc None nếu thất bại.
        """
        url = article.url

        # robots gate (AC9) — chặn trước khi fetch
        if self.respect_robots and self.robots is not None \
                and not self.robots.allowed(url):
            cap = article.metadata.setdefault("capture", {})
            cap["capture_status"] = "skipped_robots"
            article.content_text = article.summary
            self.errors.append(f"robots disallow: {url}")
            return None

        # crawl-delay (nếu robots khai) — chỉ áp khi lớn hơn default
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

        # RawStore.save — HÀNH ĐỘNG ĐẦU TIÊN sau fetch (byte-exact, no clean)
        cap = self.raw_store.save(domain, url, article.url_title_hash, resp,
                                  fetched_at=article.fetched_at)
        article.metadata["capture"] = cap

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
            article.content_html = str(node)  # vùng con tham chiếu (primary)
        else:
            # D5 density fallback — CHỈ đổi content_html; raw .html đã lưu, không đụng
            article.content_html = self._density_extract(html) or html
            cap.setdefault("missing", []).append("main_content_node")

        # D1 validity check — feed cho phase-05 (không mutate raw artifact)
        if not self._looks_complete(html, selector):
            cap["capture_status"] = "partial"
            cap.setdefault("missing", []).append("incomplete_render")
        return html

    # -- helpers --------------------------------------------------------------
    def _looks_complete(self, html: str, selector: str) -> bool:
        """Kiểm tra sơ bộ tính toàn vẹn của trang chi tiết dựa trên kích thước và nội dung.

        Args:
            html: Chuỗi HTML trang chi tiết.
            selector: Bộ chọn CSS nội dung chính.

        Returns:
            True nếu trang hiển thị đầy đủ và không chứa dấu hiệu lỗi.
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
        """Trích xuất khối nội dung chính bằng thuật toán mật độ văn bản khi bộ chọn CSS bị lệch.

        Args:
            html: Chuỗi mã nguồn HTML bài viết.

        Returns:
            Đoạn mã HTML chứa nội dung chính hoặc None nếu trích xuất thất bại.
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
