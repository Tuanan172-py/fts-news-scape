"""
l1_classifier.py — BƯỚC CODE-FIRST (deterministic) của lớp L1: nhận diện entity trong
TIÊU ĐỀ bằng khớp mã + alias (không LLM). Đây là TẦNG 1 của quy trình 2 tầng:

  Tầng 1 (file này): code khớp được entity → 'resolved', xong.
  Tầng 2 (l1_router): tiêu đề code KHÔNG khớp (needs_agent) → handoff cho agent L1.

Đặc điểm:
  - Khớp mã/tên DN/ETF/chỉ số/sàn qua registry (chính xác cao trên tiêu đề).
  - SUY RA ngành từ GICS của mã đã khớp (tin "HPG..." → ngành Thép) + ngành khớp trực tiếp.
  - KHÔNG phụ thuộc nhóm đăng ký (co_ban/fta chỉ là ví dụ; map nhóm là bước sau khi
    người dùng thực sự đăng ký).

Output = record nhận diện/tin; `needs_agent=True` ⇔ code không khớp entity nào.
"""
from __future__ import annotations

from src.agent.entities import EntityRegistry, load_registry

L1_SCHEMA_VERSION = "1.0"

_SECURITY = {"TICKER", "ETF", "SECURITY_OTHER"}
_INDUSTRY = {"INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3", "SECTOR_FPA"}
_MARKET = {"INDEX", "EXCHANGE"}


def title_of(article: dict) -> str:
    """Rút tiêu đề: field `title` -> heading level 1 (silver) -> dòng đầu cleaned_text."""
    if article.get("title"):
        return str(article["title"]).strip()
    for h in article.get("structure", {}).get("headings", []):
        if h.get("level") == 1 and h.get("text"):
            return str(h["text"]).strip()
    ct = article.get("cleaned_text", "")
    return ct.split("\n", 1)[0].strip() if ct else ""


def classify_title(title: str, reg: EntityRegistry | None = None) -> dict:
    """Phân loại 1 tiêu đề → record entity/ngành/nhóm đăng ký (không cần article_id)."""
    reg = reg or load_registry()
    dets = reg.detect(title)
    ids = [d["entity_id"] for d in dets]
    types = sorted({d["type"] for d in dets})

    # ngành: khớp trực tiếp (INDUSTRY_*/SECTOR_FPA) + suy ra từ GICS của mã đã khớp
    industries: set[str] = set()
    for d in dets:
        if d["type"] in _INDUSTRY:
            industries.add(d["canonical_name"])
        attrs = reg.entities[d["entity_id"]]["attributes"]
        for k in ("gics1", "gics2", "gics3"):
            if attrs.get(k):
                industries.add(attrs[k])

    # mức độ liên quan (ưu tiên có mã/DN > ngành > chỉ mang tính thị trường)
    tset = set(types)
    if _SECURITY & tset:
        relevance = "entity"
    elif _INDUSTRY & tset:
        relevance = "industry"
    elif _MARKET & tset:
        relevance = "market"
    else:
        relevance = "none"

    # entity chính: mã/DN đầu tiên, không thì entity đầu tiên bất kỳ
    primary = next((d["entity_id"] for d in dets if d["type"] in _SECURITY), None)
    if primary is None and dets:
        primary = dets[0]["entity_id"]

    return {
        "l1_schema_version": L1_SCHEMA_VERSION,
        "title": title,
        "entities": dets,
        "entity_ids": ids,
        "entity_types": types,
        "industries": sorted(industries),
        "primary_entity": primary,
        "relevance": relevance,
        # code-first không khớp entity nào ⇒ chuyển handoff cho agent L1
        "needs_agent": len(ids) == 0,
    }


def classify_article(article: dict, reg: EntityRegistry | None = None) -> dict:
    """Phân loại 1 article (silver dict hoặc record có `title`)."""
    reg = reg or load_registry()
    rec = classify_title(title_of(article), reg)
    rec["article_id"] = article.get("article_id")
    rec["domain"] = article.get("domain")
    return rec
