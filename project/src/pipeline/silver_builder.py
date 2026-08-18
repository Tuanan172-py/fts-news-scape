"""
SilverBuilder — chuẩn hoá Bronze raw thành "clean base" (Silver) cho agent.

PURE + OFFLINE + DETERMINISTIC: input = meta.json dict + raw bytes; không network,
không đọc DB. Cùng raw → cùng silver (built_at lấy từ meta.fetch_ts, không dùng now)
→ re-derive được sau khi sửa parser. Xem phase-01, docs/design/07.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.processor.extractor import extract_content, extract_text

SILVER_SCHEMA_VERSION = "1.0"

# ký tự đặc trưng tiếng Việt (đủ để phân biệt vi vs und cho heuristic nhẹ)
_VI_CHARS = re.compile(r"[ăâđêôơưÁÀẢÃẠáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)
_EN_STOPWORDS = re.compile(r"\b(the|and|of|to|in|for|is|on|with|that|as|by)\b", re.I)
# ngưỡng độ dài cleaned_text để chấm chất lượng trích (bug #2)
_MIN_HIGH = 200   # trafilatura cho ≥ ký tự này → high
_MIN_OK = 50      # dưới ngưỡng này coi như trích hụt → thử fallback sâu hơn


def _detect_lang(text: str) -> str:
    if not text:
        return "und"
    sample = text[:2000]
    if len(_VI_CHARS.findall(sample)) >= 5:
        return "vi"
    # EN heuristic (bug #4a): nhiều chữ ASCII + stopword tiếng Anh
    ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    if ascii_letters >= 20 and _EN_STOPWORDS.search(sample):
        return "en"
    return "und"


def _domain_of(meta: dict) -> str:
    """Domain lưu trữ. Ưu tiên path Bronze (đồng bộ partition), fallback source_url
    netloc (bug #4b: đổi tên thư mục base không còn làm domain rỗng)."""
    html_path = meta.get("html_path", "")
    if html_path:
        parts = html_path.replace("\\", "/").split("/")
        if "raw_html" in parts:
            i = parts.index("raw_html")
            if i + 1 < len(parts):
                return parts[i + 1]
    net = urlparse(meta.get("source_url", "")).netloc.lower()
    return net[4:] if net.startswith("www.") else net


def _parse_structure(html: str) -> dict:
    """Best-effort DOM structure (OPTIONAL field). BeautifulSoup only, no exec."""
    soup = BeautifulSoup(html, "lxml")
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


class SilverBuilder:
    schema_version = SILVER_SCHEMA_VERSION

    def build(self, meta: dict, raw_bytes: bytes) -> dict:
        """meta = capture .meta.json dict; raw_bytes = Bronze .html bytes."""
        encoding = meta.get("encoding") or "utf-8"
        try:
            html = raw_bytes.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            html = raw_bytes.decode("utf-8", errors="replace")

        url = meta.get("source_url", "")
        structure = _parse_structure(html)               # parse 1 lần, tái dùng làm fallback
        cleaned, quality = self._extract_cleaned(url, html, structure)

        return {
            "silver_schema_version": self.schema_version,
            "article_id": meta.get("url_title_hash", ""),
            "source_url": url,
            "domain": _domain_of(meta),
            "content_sha256": meta.get("content_sha256", ""),
            "cleaned_text": cleaned,
            "extraction_quality": quality,               # bug #2: high|medium|low|empty
            "structure": structure,
            "images": meta.get("images", []),
            "language": _detect_lang(cleaned),
            "built_at": meta.get("fetch_ts", ""),       # từ Bronze → deterministic
            "built_from_raw_path": meta.get("html_path", ""),
        }

    @staticmethod
    def _extract_cleaned(url: str, html: str, structure: dict) -> tuple[str, str]:
        """Chuỗi fallback đảm bảo cleaned_text không rỗng khi trang có chữ (bug #2).

        trafilatura(high) → extract_text/BS4(medium) → join paragraphs(low) → empty.
        Trả (cleaned_text, extraction_quality).
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
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_silver(silver: dict, base_dir: str = "data/silver") -> str:
    """Ghi silver.json mirror partition Bronze. Trả path."""
    domain = silver.get("domain") or "unknown"
    yyyymmdd = ""
    if silver.get("built_from_raw_path"):
        parts = silver["built_from_raw_path"].replace("\\", "/").split("/")
        if len(parts) >= 2:
            yyyymmdd = parts[-2]
    directory = os.path.join(base_dir, domain, yyyymmdd or "unknown-date")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{silver['article_id']}.json")
    _atomic_write(path, json.dumps(silver, ensure_ascii=False, indent=2).encode("utf-8"))
    return path
