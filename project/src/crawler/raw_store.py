"""Store raw Bronze artifacts (original HTML and binaries) together with their metadata files."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from src.core import paths

# Response headers to keep, so that no sensitive header is stored.
_HEADER_WHITELIST = ("content-type", "content-length", "last-modified",
                     "etag", "server", "date")
# Image attributes tried in order when resolving the image URL.
_LAZY_ATTRS = ("src", "data-src", "data-original", "original-src",
               "document-path", "data-lazy")


class RawStore:
    """Store byte-exact raw Bronze data and its accompanying metadata.

    Attributes:
        base_dir: Absolute path of the root directory of the Bronze raw data.
    """

    def __init__(self, base_dir: str | os.PathLike | None = None):
        """Initialize the Bronze store, anchoring a relative path to the data root.

        A relative path is not resolved against the current working directory, because a
        process running in another directory would write Bronze outside the place Silver reads.

        Args:
            base_dir: Bronze root directory, absolute or relative to the data root.
                Defaults to `paths.bronze_dir()`.
        """
        root = paths.resolve_data_path(base_dir) if base_dir else paths.bronze_dir()
        self.base_dir = str(root)

    @staticmethod
    def _portable_path(path: str) -> str:
        """Convert a path under the data root to a relative path for the meta file.

        Args:
            path: Bronze file path.

        Returns:
            Path relative to the data root if the file is inside it, otherwise unchanged.
        """
        return paths.to_data_relative(path)

    @staticmethod
    def _yyyymmdd(fetched_at: str) -> str:
        try:
            return datetime.fromisoformat(fetched_at).strftime("%Y%m%d")
        except (ValueError, TypeError):
            return "unknown-date"

    def _dir_for(self, domain: str, yyyymmdd: str) -> str:
        """Create and return the storage directory for a domain and date.

        Args:
            domain: Domain of the news source.
            yyyymmdd: Date string in YYYYMMDD format.

        Returns:
            Path of the storage directory.
        """
        d = os.path.join(self.base_dir, domain, yyyymmdd)
        os.makedirs(d, exist_ok=True)
        return d

    def paths_for(self, domain: str, url_title_hash: str, fetched_at: str) -> tuple[str, str]:
        """Determine the HTML and metadata file paths without creating directories.

        Args:
            domain: Domain of the news source.
            url_title_hash: Hash that identifies the article.
            fetched_at: ISO fetch time.

        Returns:
            Tuple (html_path, meta_path) of path strings.
        """
        d = os.path.join(self.base_dir, domain, self._yyyymmdd(fetched_at))
        base = os.path.join(d, url_title_hash)
        return f"{base}.html", f"{base}.meta.json"

    @staticmethod
    def _has_good_capture(html_path: str, meta_path: str) -> bool:
        """Check whether a good capture (`ok` or `partial`) with its HTML file exists at this path.

        Args:
            html_path: Bronze HTML file path.
            meta_path: Bronze meta file path.

        Returns:
            True if the meta is readable, its status is `ok` or `partial` and the HTML exists.
        """
        if not (os.path.exists(html_path) and os.path.exists(meta_path)):
            return False
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f).get("capture_status") in ("ok", "partial")
        except (OSError, ValueError):
            return False

    @staticmethod
    def _write_atomic(path: str, data: bytes) -> None:
        """Write data to a temp file and atomically replace the destination, with retries.

        Args:
            path: Destination file path.
            data: Bytes to write.
        """
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                os.replace(tmp, path)  # atomic on the same volume
                return
            except PermissionError as e:  # Windows file lock: retry briefly
                last_err = e
                time.sleep(0.1 * (attempt + 1))
        try:
            os.remove(tmp)  # remove the leftover temp file before raising
        except OSError:
            pass
        raise last_err  # type: ignore[misc]

    @staticmethod
    def _filter_headers(headers) -> dict:
        """Keep only the whitelisted response headers.

        Args:
            headers: Response headers mapping.

        Returns:
            Whitelisted headers as strings.
        """
        out: dict = {}
        getter = getattr(headers, "get", None)
        if getter is None:
            return out
        for k in _HEADER_WHITELIST:
            v = headers.get(k)
            if v is not None:
                out[k] = str(v)
        return out

    # -- image manifest (read-only, does not modify the artifact) --------------
    @staticmethod
    def _scan_images(body: bytes, base_url: str) -> list[dict]:
        """Scan the HTML for images and resolve their URLs and captions.

        Args:
            body: HTML bytes.
            base_url: Page URL used to resolve relative image URLs.

        Returns:
            One dict per image with its outer tag, resolved URL, alt, title and caption.
        """
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
        """Store the original raw HTML and its sidecar .meta.json metadata file.

        Args:
            domain: Domain of the news source.
            url: Original article URL.
            url_title_hash: Hash that identifies the article.
            response: HTTP response, or None when the fetch failed.
            fetched_at: Fetch time as an ISO string.
            missing: Optional list of missing content parts.
            protection: Optional protection mechanism that was detected.
            render_method: Content render method.

        Returns:
            Dict with the capture status of the article.
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
            if not self._has_good_capture(html_path, meta_path):
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
            # 404/410 means the source deleted the article (not a transient error). It is kept
            # separate so that (a) backfill_deferred does not retry it uselessly and (b) the
            # "published then deleted" frequency typical of Vietnamese news can be measured
            # (pipeline_radar).
            deleted_at_source = status in (404, 410)
            cap["error"] = {
                "type": "deleted_at_source" if deleted_at_source else "http_error",
                "http_status": status,
                "message": f"status {status}" if status is not None else "empty body",
                "protection_mechanism": protection,
            }
            if deleted_at_source:
                cap["capture_status"] = "deleted_at_source"
            if not cap["missing"]:
                cap["missing"] = ["article_body"]
            # A failed fetch must not overwrite an existing good capture: Bronze is immutable.
            if self._has_good_capture(html_path, meta_path):
                return cap
            if len(body) > 0:  # a partial body is still stored for inspection
                self._write_atomic(html_path, body)
                cap["content_sha256"] = hashlib.sha256(body).hexdigest()
            self._write_meta(meta_path, cap)
            return cap

        # success: write the raw bytes unchanged
        self._write_atomic(html_path, body)
        cap["content_sha256"] = hashlib.sha256(body).hexdigest()
        cap["images"] = self._scan_images(body, url)  # read-only, does not modify the file
        cap["capture_status"] = "partial" if cap["missing"] else "ok"
        self._write_meta(meta_path, cap)
        return cap

    # -- binary attachments (design 16: NSO .xlsx/.docx/.pdf) -------------------
    _EXT_BY_TYPE = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/msword": ".doc",
        "application/zip": ".zip",
    }

    def save_binary(self, domain: str, url: str, key: str, response,
                    *, fetched_at: str) -> dict:
        """Store a binary attachment and its .binmeta.json metadata file.

        Args:
            domain: Domain of the news source.
            url: Attachment URL.
            key: Unique key identifying the attachment.
            response: HTTP response holding the binary content.
            fetched_at: Fetch time as an ISO string.

        Returns:
            Dict with the capture status of the binary file.
        """
        yyyymmdd = self._yyyymmdd(fetched_at)
        directory = self._dir_for(domain, yyyymmdd)

        status = getattr(response, "status_code", None) if response is not None else None
        headers = getattr(response, "headers", {}) if response is not None else {}
        ctype = str((headers or {}).get("content-type", "")).split(";")[0].strip().lower()
        ext = self._EXT_BY_TYPE.get(ctype, "")
        if not ext:
            tail = os.path.splitext(urlparse(url).path)[1].lower()
            ext = tail if tail in {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".zip"} else ".bin"

        bin_path = os.path.join(directory, f"{key}{ext}")
        # The .binmeta.json suffix is reserved for binary files so the derive pipeline's rglob *.meta.json does not pick them up.
        meta_path = os.path.join(directory, f"{key}{ext}.binmeta.json")

        cap: dict = {
            "source_url": url,
            "key": key,
            "fetch_ts": fetched_at,
            "render_method": "requests",
            "binary_path": bin_path,
            "http_status": status,
            "content_type": ctype,
            "content_sha256": None,
            "content_length_bytes": 0,
            "response_headers": self._filter_headers(headers),
            "capture_status": "failed",
            "error": None,
        }

        body = getattr(response, "content", b"") if response is not None else b""
        if isinstance(body, str):
            body = body.encode("utf-8", errors="replace")
        body = body or b""

        if response is None or status is None or not (200 <= status < 300) or not body:
            cap["error"] = {
                "type": "fetch_failed" if response is None else "http_error",
                "http_status": status,
                "message": "no response" if response is None else f"status {status}",
            }
            self._write_meta(meta_path, cap)
            return cap

        self._write_atomic(bin_path, body)           # bytes unchanged, not parsed
        cap["content_length_bytes"] = len(body)
        cap["content_sha256"] = hashlib.sha256(body).hexdigest()
        cap["capture_status"] = "ok"
        self._write_meta(meta_path, cap)
        return cap

    def _write_meta(self, path: str, cap: dict) -> None:
        """Write the capture metadata as JSON, storing `html_path` in portable form.

        Args:
            path: Meta file path.
            cap: Capture dict to write.
        """
        portable = dict(cap)
        if portable.get("html_path"):
            portable["html_path"] = self._portable_path(portable["html_path"])
        data = json.dumps(portable, ensure_ascii=False, indent=2).encode("utf-8")
        self._write_atomic(path, data)
