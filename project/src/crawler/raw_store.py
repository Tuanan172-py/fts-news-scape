"""
RawStore — lưu raw HTML byte-exact + sidecar .meta.json TRƯỚC mọi xử lý.

Nguyên tắc (spec capture §7 no-clean): file .html giữ NGUYÊN bytes phản hồi —
không decode, không strip tag, không rewrite attribute, không normalize. Đây là
artifact có thể kiểm tra độc lập (offline) với trang gốc.

`images[]` trong meta.json là READ-ONLY scan (BeautifulSoup) — chỉ liệt kê ảnh
(URL + alt/title/caption) để bước sau tải/tái sử dụng. Việc swap data-src→src là
việc của pipeline xử lý downstream, KHÔNG làm ở đây; artifact không bao giờ bị sửa.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

# Q5: chỉ giữ subset header — loại Set-Cookie/Authorization (PII/secret hygiene)
_HEADER_WHITELIST = ("content-type", "content-length", "last-modified",
                     "etag", "server", "date")
# thứ tự ưu tiên resolve URL ảnh (lazy-load VN news: data-src/data-original...)
_LAZY_ATTRS = ("src", "data-src", "data-original", "original-src",
               "document-path", "data-lazy")


class RawStore:
    """Ghi raw HTML + metadata sidecar. Không raise — lỗi trả trong dict `capture`."""

    def __init__(self, base_dir: str = "data/raw_html"):
        self.base_dir = base_dir

    # -- path helpers ---------------------------------------------------------
    @staticmethod
    def _yyyymmdd(fetched_at: str) -> str:
        try:
            return datetime.fromisoformat(fetched_at).strftime("%Y%m%d")
        except (ValueError, TypeError):
            return "unknown-date"

    def _dir_for(self, domain: str, yyyymmdd: str) -> str:
        """
            Giải thích: Tạo đường dẫn thư mục cho một domain và ngày cụ thể.
        """
        d = os.path.join(self.base_dir, domain, yyyymmdd)
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def _write_atomic(path: str, data: bytes) -> None:
        """
            Giải thích: Ghi dữ liệu vào một tệp tạm thời và sau đó thay thế tệp đích, đảm bảo quy trình đọc - ghi không làm ảnh hướng tệp đích
        """
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)  # atomic trên cùng volume

    @staticmethod
    def _filter_headers(headers) -> dict:
        out: dict = {}
        getter = getattr(headers, "get", None)
        if getter is None:
            return out
        for k in _HEADER_WHITELIST:
            v = headers.get(k)
            if v is not None:
                out[k] = str(v)
        return out

    # -- image manifest (read-only, không sửa artifact) -----------------------
    @staticmethod
    def _scan_images(body: bytes, base_url: str) -> list[dict]:
        try:
            soup = BeautifulSoup(body, "lxml")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("raw_store image scan failed {}: {}", base_url, e)
            return []
        images: list[dict] = []
        for img in soup.find_all("img"):
            resolved = ""
            for attr in _LAZY_ATTRS:
                val = img.get(attr)
                if val:
                    resolved = val.strip()
                    break
            if not resolved:
                srcset = img.get("srcset", "")
                if srcset:
                    resolved = srcset.split(",")[0].strip().split(" ")[0]
            if resolved and base_url:
                resolved = urljoin(base_url, resolved)
            caption = ""
            fig = img.find_parent("figure")
            if fig is not None:
                cap_el = fig.find("figcaption")
                if cap_el is not None:
                    caption = cap_el.get_text(" ", strip=True)
            images.append({
                "outer_tag": str(img),
                "resolved_url": resolved,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
                "caption": caption,
            })
        return images

    # -- main API -------------------------------------------------------------
    def save(self, domain: str, url: str, url_title_hash: str, response,
             *, fetched_at: str, missing: list[str] | None = None,
             protection: str | None = None, render_method: str = "requests") -> dict:
        """Lưu raw artifact + meta.json; trả dict `capture` (không kèm body).

        response: requests.Response-like (status_code/content/headers/encoding/ok)
        hoặc None (fetch fail). Luôn ghi meta.json — kể cả khi failed.
        """
        yyyymmdd = self._yyyymmdd(fetched_at)
        directory = self._dir_for(domain, yyyymmdd)
        html_path = os.path.join(directory, f"{url_title_hash}.html")
        meta_path = os.path.join(directory, f"{url_title_hash}.meta.json")

        cap: dict = {
            "source_url": url,
            "url_title_hash": url_title_hash,
            "fetch_ts": fetched_at,
            "render_method": render_method,
            "html_path": html_path,
            "http_status": None,
            "content_sha256": None,
            "content_length_bytes": 0,
            "encoding": None,
            "response_headers": {},
            "images": [],
            "capture_status": "failed",
            "missing": list(missing or []),
            "error": None,
        }

        if response is None:
            cap["error"] = {"type": "fetch_failed", "http_status": None,
                            "message": "no response",
                            "protection_mechanism": protection}
            if not cap["missing"]:
                cap["missing"] = ["article_body"]
            self._write_meta(meta_path, cap)
            return cap

        status = getattr(response, "status_code", None)
        body = getattr(response, "content", b"") or b""
        if isinstance(body, str):
            body = body.encode(getattr(response, "encoding", None) or "utf-8",
                               errors="replace")
        cap["http_status"] = status
        cap["content_length_bytes"] = len(body)
        cap["encoding"] = getattr(response, "encoding", None)
        cap["response_headers"] = self._filter_headers(getattr(response, "headers", {}))

        ok = status is not None and 200 <= status < 300 and len(body) > 0
        if not ok:
            cap["error"] = {
                "type": "http_error", "http_status": status,
                "message": f"status {status}" if status is not None else "empty body",
                "protection_mechanism": protection,
            }
            if not cap["missing"]:
                cap["missing"] = ["article_body"]
            if len(body) > 0:  # partial body vẫn lưu để inspect
                self._write_atomic(html_path, body)
                cap["content_sha256"] = hashlib.sha256(body).hexdigest()
            self._write_meta(meta_path, cap)
            return cap

        # success — ghi raw bytes NGUYÊN BẢN
        self._write_atomic(html_path, body)
        cap["content_sha256"] = hashlib.sha256(body).hexdigest()
        cap["images"] = self._scan_images(body, url)  # read-only, không sửa file
        cap["capture_status"] = "partial" if cap["missing"] else "ok"
        self._write_meta(meta_path, cap)
        return cap

    def _write_meta(self, path: str, cap: dict) -> None:
        data = json.dumps(cap, ensure_ascii=False, indent=2).encode("utf-8")
        self._write_atomic(path, data)
