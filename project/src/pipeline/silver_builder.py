"""Bộ tinh chế dữ liệu thô Bronze thành cấu trúc Silver chuẩn hóa.

Chuyển đổi các tệp tin HTML/JSON thô tầng Bronze thành dữ liệu sạch
(Silver) có cấu trúc, tách lọc tiêu đề, nội dung văn bản và cấu trúc DOM.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

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
    """Trích xuất chuỗi HTML thân bài từ dữ liệu JSON thô.

    Args:
        raw_text: Chuỗi định dạng JSON thô thu được từ API.

    Returns:
        Chuỗi HTML thân bài viết, hoặc None nếu không trích xuất được.
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
    """Nhận diện mã ngôn ngữ ('vi', 'en', hoặc 'und') của văn bản."""
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


def _parse_structure_from(soup) -> dict:
    """Best-effort DOM structure (OPTIONAL field). BeautifulSoup only, no exec."""
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
    """Ung vien tieu de, uu tien nguon dang tin cay nhat truoc."""
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
        # nhieu bao gan hau to toa soan: 'Tieu de | CafeF', 'Tieu de - Vietstock'
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
    """(title, da_kiem_chung).

    `url_title_hash` = sha256(url + title) do scraper tinh luc cao, va no NAM SAN trong
    meta.json. Nho vay Silver CHUNG MINH duoc ung vien nao la tieu de that thay vi doan —
    van thuan tuy, offline, tat dinh.

    Vi sao can: work-package truoc day khong co truong `title`, nen title_of() roi ve h1 dau
    tien. Voi trang cong bo thong tin cua cafef, h1 la header trang HO SO DOANH NGHIEP
    ("Ngan hang TMCP Phat trien T.P Ho Chi Minh (HOSE)") chu khong phai tieu de bai
    ("HDB: Thong bao thay doi dia diem..."). Do tren monocle.db: 122/1.320 bai lech,
    va bai HDB vi the MAT ca TICKER:HDB — dung tieu de that thi khop ngay bang ma.

    Khong ung vien nao khop hash (toa soan sua tit sau khi cao) -> lay ung vien dau tien,
    danh dau chua kiem chung de con truy vet.
    """
    cands = _title_candidates(soup, structure, cleaned)
    if url and url_title_hash:
        for c in cands:
            if sha256_hash(url, c) == url_title_hash:
                return c, True
    return (cands[0] if cands else ""), False


class SilverBuilder:
    """Bộ chuyển đổi và tinh chế dữ liệu thô Bronze sang cấu trúc chuẩn Silver.

    Attributes:
        schema_version: Phiên bản cấu trúc lược đồ Silver.
    """

    schema_version = SILVER_SCHEMA_VERSION

    def build(self, meta: dict, raw_bytes: bytes) -> dict:
        """Thực hiện tinh chế dữ liệu thô và siêu dữ liệu Bronze thành bản ghi Silver.

        Args:
            meta: Từ điển chứa siêu dữ liệu tệp .meta.json của tầng Bronze.
            raw_bytes: Chuỗi bytes nội dung tệp thô .html/.json từ tầng Bronze.

        Returns:
            Từ điển chứa dữ liệu sạch tầng Silver theo lược đồ silver-v1.
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
        """Chuỗi dự phòng trích xuất văn bản đảm bảo không rỗng."""
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
    """Ghi dữ liệu nguyên tử thông qua tệp tin tạm thời."""
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_silver(silver: dict, base_dir: str = "data/silver") -> str:
    """Lưu trữ đối tượng Silver ra đĩa theo cấu trúc phân vùng tên miền và ngày tháng.

    Args:
        silver: Từ điển dữ liệu Silver đã tinh chế.
        base_dir: Thư mục gốc lưu trữ dữ liệu tầng Silver.

    Returns:
        Đường dẫn tới tệp tin Silver JSON đã lưu.
    """
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
