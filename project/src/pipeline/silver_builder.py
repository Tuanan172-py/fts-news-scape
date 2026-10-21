"""Convert raw Bronze HTML/JSON files into structured Silver records with the title, clean text and DOM structure."""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.core import paths
from src.core.models import sha256_hash
from src.processor.extractor import extract_content, extract_text

SILVER_SCHEMA_VERSION = "1.0"

_VI_CHARS = re.compile(r"[ăâđêôơưÁÀẢÃẠáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)
_EN_STOPWORDS = re.compile(r"\b(the|and|of|to|in|for|is|on|with|that|as|by)\b", re.I)
_MIN_HIGH = 200
_MIN_OK = 50
_WS = re.compile(r"\s+")

_JSON_HTML_FIELDS = ("content", "originalContent", "original_content",
                     "body_html", "content_html", "body", "html")


def _html_from_json(raw_text: str) -> str | None:
    """Extract the article body HTML string from raw JSON data.

    Args:
        raw_text: Raw JSON string obtained from an API.

    Returns:
        Article body HTML string, or None when nothing can be extracted.
    """
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else None
    if not isinstance(data, dict):
        return None
    for field in _JSON_HTML_FIELDS:
        val = data.get(field)
        if isinstance(val, str) and val.strip():
            return val
    return None


def _detect_lang(text: str) -> str:
    """Detect the language code ('vi', 'en' or 'und') of a text.

    Args:
        text: Text to inspect; only the first 2000 characters are sampled.

    Returns:
        'vi', 'en' or 'und' when undetermined.
    """
    if not text:
        return "und"
    sample = text[:2000]
    if len(_VI_CHARS.findall(sample)) >= 5:
        return "vi"
    # English heuristic: many ASCII letters plus English stopwords.
    ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    if ascii_letters >= 20 and _EN_STOPWORDS.search(sample):
        return "en"
    return "und"


def _domain_of(meta: dict) -> str:
    """Return the storage domain of an article.

    Prefers the Bronze path (keeps partitions in sync) and falls back to the netloc of
    `source_url`, so renaming the base directory does not yield an empty domain.

    Args:
        meta: Bronze metadata dict.

    Returns:
        Domain name, or an empty string when neither source yields one.
    """
    html_path = meta.get("html_path", "")
    if html_path:
        parts = html_path.replace("\\", "/").split("/")
        if "raw_html" in parts:
            i = parts.index("raw_html")
            if i + 1 < len(parts):
                return parts[i + 1]
    net = urlparse(meta.get("source_url", "")).netloc.lower()
    return net[4:] if net.startswith("www.") else net


def _parse_structure_from(soup) -> dict:
    """Extract a best-effort DOM structure (optional field) using BeautifulSoup only, with no script execution.

    Args:
        soup: Parsed BeautifulSoup document.

    Returns:
        Dict with the keys headings, paragraphs, tables and links.
    """
    body = soup.body or soup
    headings = [{"level": int(h.name[1]), "text": h.get_text(" ", strip=True)}
                for h in body.find_all(re.compile(r"^h[1-6]$"))
                if h.get_text(strip=True)]
    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")
                  if p.get_text(strip=True)]
    tables = []
    for tbl in body.find_all("table"):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [c.get_text(" ", strip=True)
                     for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    links = [{"href": a.get("href", ""), "text": a.get_text(" ", strip=True)}
             for a in body.find_all("a", href=True)]
    return {"headings": headings, "paragraphs": paragraphs,
            "tables": tables, "links": links}


def _title_candidates(soup, structure: dict, cleaned: str) -> list[str]:
    """List title candidates, most trustworthy sources first.

    Args:
        soup: Parsed BeautifulSoup document.
        structure: DOM structure dict from `_parse_structure_from`.
        cleaned: Clean article text; its first line is the last candidate.

    Returns:
        Distinct candidate titles in priority order.
    """
    out: list[str] = []

    def add(v):
        v = _WS.sub(" ", str(v or "")).strip()
        if v and v not in out:
            out.append(v)

    for attr, name in (("property", "og:title"), ("name", "twitter:title"),
                       ("name", "title"), ("itemprop", "headline")):
        for tag in soup.find_all("meta", attrs={attr: name}):
            add(tag.get("content"))
    if soup.title:
        raw = soup.title.get_text(" ", strip=True)
        add(raw)
        # Many outlets append a publisher suffix: 'Title | CafeF', 'Title - Vietstock'.
        for sep in ("|", " - ", " – ", " — "):
            if sep in raw:
                add(raw.rsplit(sep, 1)[0])
    for h in structure.get("headings") or []:
        add(h.get("text"))
    if cleaned:
        add(cleaned.split(chr(10), 1)[0])
    return out


def _resolve_title(soup, structure: dict, cleaned: str,
                   url: str, url_title_hash: str) -> tuple[str, bool]:
    """Resolve the article title and whether it is verified.

    `url_title_hash` = sha256(url + title) is computed by the scraper at capture time and is
    stored in meta.json. Silver can therefore prove which candidate is the real title instead
    of guessing, in a pure, offline and deterministic way.

    Rationale: the work package had no `title` field, so title_of() fell back to the first
    h1. On cafef disclosure pages the h1 is the COMPANY PROFILE page header
    ("Ngan hang TMCP Phat trien T.P Ho Chi Minh (HOSE)") rather than the article title
    ("HDB: Thong bao thay doi dia diem..."). Measured on monocle.db: 122 of 1,320 articles
    were wrong, and the HDB article lost its TICKER:HDB match; with the real title the ticker
    matches immediately.

    When no candidate matches the hash (the newsroom edited the title after capture), the
    first candidate is returned and flagged as unverified so it stays traceable.

    Args:
        soup: Parsed BeautifulSoup document.
        structure: DOM structure dict from `_parse_structure_from`.
        cleaned: Clean article text.
        url: Source URL of the article.
        url_title_hash: Hash recorded by the scraper at capture time.

    Returns:
        Tuple of the title and a flag that is True when the title matched the hash.
    """
    cands = _title_candidates(soup, structure, cleaned)
    if url and url_title_hash:
        for c in cands:
            if sha256_hash(url, c) == url_title_hash:
                return c, True
    return (cands[0] if cands else ""), False


class SilverBuilder:
    """Convert raw Bronze data into the standard Silver structure.

    Attributes:
        schema_version: Version of the Silver schema.
    """

    schema_version = SILVER_SCHEMA_VERSION

    def build(self, meta: dict, raw_bytes: bytes) -> dict:
        """Convert raw data and Bronze metadata into a Silver record.

        Args:
            meta: Dict with the Bronze .meta.json metadata.
            raw_bytes: Bytes of the raw .html/.json file from the Bronze layer.

        Returns:
            Dict with the clean Silver data following the silver-v1 schema.
        """
        encoding = meta.get("encoding") or "utf-8"
        try:
            html = raw_bytes.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            html = raw_bytes.decode("utf-8", errors="replace")

        url = meta.get("source_url", "")
        ctype = str((meta.get("response_headers") or {}).get("content-type", "")).lower()
        if "json" in ctype:
            inner = _html_from_json(html)
            if inner is not None:
                html = inner

        soup = BeautifulSoup(html, "lxml")
        structure = _parse_structure_from(soup)
        cleaned, quality = self._extract_cleaned(url, html, structure)
        title, title_verified = _resolve_title(
            soup, structure, cleaned, url, meta.get("url_title_hash", ""))

        return {
            "silver_schema_version": self.schema_version,
            "article_id": meta.get("url_title_hash", ""),
            "source_url": url,
            "domain": _domain_of(meta),
            "content_sha256": meta.get("content_sha256", ""),
            "title": title,
            "title_verified": title_verified,
            "cleaned_text": cleaned,
            "extraction_quality": quality,
            "structure": structure,
            "images": meta.get("images", []),
            "language": _detect_lang(cleaned),
            "built_at": meta.get("fetch_ts", ""),
            "built_from_raw_path": meta.get("html_path", ""),
        }

    @staticmethod
    def _extract_cleaned(url: str, html: str, structure: dict) -> tuple[str, str]:
        """Extract clean text through a fallback chain that avoids an empty result.

        Args:
            url: Source URL of the article.
            html: Article HTML.
            structure: DOM structure dict; its paragraphs are the last fallback.

        Returns:
            Tuple of the clean text and its quality ('high', 'medium', 'low' or 'empty').
        """
        cleaned = (extract_content(url, html=html).get("content") or "").strip()
        quality = "high"
        if len(cleaned) < _MIN_HIGH:
            alt = (extract_text(html) or "").strip()
            if len(alt) > len(cleaned):
                cleaned, quality = alt, "medium"
        if len(cleaned) < _MIN_OK:
            joined = "\n".join(structure.get("paragraphs", [])).strip()
            if len(joined) > len(cleaned):
                cleaned, quality = joined, "low"
        if not cleaned:
            quality = "empty"
        return cleaned, quality


def _atomic_write(path: str, data: bytes) -> None:
    """Write data atomically through a temporary file with retries.

    Args:
        path: Destination file path.
        data: Bytes to write.

    Raises:
        OSError: If the temporary file cannot be moved into place after all retries.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            os.replace(tmp, path)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(0.15 * (attempt + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    if last_err is not None:
        raise last_err


def write_silver(silver: dict, base_dir: str | None = None) -> str:
    """Write a Silver object to disk, partitioned by domain and date.

    Args:
        silver: Derived Silver data dict.
        base_dir: Root directory of the Silver layer. Defaults to `paths.silver_dir()`.

    Returns:
        Path of the saved Silver JSON file.
    """
    domain = silver.get("domain") or "unknown"
    yyyymmdd = ""
    if silver.get("built_from_raw_path"):
        parts = silver["built_from_raw_path"].replace("\\", "/").split("/")
        if len(parts) >= 2:
            yyyymmdd = parts[-2]
    root = paths.resolve_data_path(base_dir) if base_dir else paths.silver_dir()
    directory = os.path.join(str(root), domain, yyyymmdd or "unknown-date")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{silver['article_id']}.json")
    _atomic_write(path, json.dumps(silver, ensure_ascii=False, indent=2).encode("utf-8"))
    return path
