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

from bs4 import BeautifulSoup

from src.processor.extractor import extract_content, extract_text

SILVER_SCHEMA_VERSION = "1.0"

# ký tự đặc trưng tiếng Việt (đủ để phân biệt vi vs und cho heuristic nhẹ)
_VI_CHARS = re.compile(r"[ăâđêôơưÁÀẢÃẠáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)


def _detect_lang(text: str) -> str:
    if not text:
        return "und"
    sample = text[:2000]
    return "vi" if len(_VI_CHARS.findall(sample)) >= 5 else "und"


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
        result = extract_content(url, html=html)          # trafilatura (reuse)
        cleaned = result.get("content") or extract_text(html)

        domain = ""
        if meta.get("html_path"):
            # data/raw_html/<domain>/<yyyymmdd>/<hash>.html
            parts = meta["html_path"].replace("\\", "/").split("/")
            if "raw_html" in parts:
                i = parts.index("raw_html")
                if i + 1 < len(parts):
                    domain = parts[i + 1]

        return {
            "silver_schema_version": self.schema_version,
            "article_id": meta.get("url_title_hash", ""),
            "source_url": url,
            "domain": domain,
            "content_sha256": meta.get("content_sha256", ""),
            "cleaned_text": cleaned,
            "structure": _parse_structure(html),
            "images": meta.get("images", []),
            "language": _detect_lang(cleaned),
            "built_at": meta.get("fetch_ts", ""),       # từ Bronze → deterministic
            "built_from_raw_path": meta.get("html_path", ""),
        }


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
