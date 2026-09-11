"""Bộ phân loại thực thể ban đầu dựa trên quy tắc mã nguồn (Code-First Classifier).

Thực hiện nhận diện tất định các thực thể tài chính xuất hiện trong tiêu đề
bài viết (mã chứng khoán, ngành, tài sản, tổ chức) qua EntityRegistry trước khi chuyển giao cho Agent.
"""
from __future__ import annotations

from src.agent.entities import EntityRegistry, load_registry

L1_SCHEMA_VERSION = "1.0"

_SECURITY = {"TICKER", "ETF", "SECURITY_OTHER"}
_INDUSTRY = {"INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3"}
_ASSET = {"ASSET_CLASS"}
_INST = {"INSTITUTION"}
_MACRO = {"MACRO_GEO", "MACRO_THEME"}
_MARKET = {"INDEX", "EXCHANGE"}


def title_of(article: dict) -> str:
    """Trích xuất tiêu đề bài viết với cơ chế dự phòng nhiều tầng.

    Args:
        article: Từ điển dữ liệu bài viết (tầng Silver hoặc gói công việc).

    Returns:
        Chuỗi tiêu đề bài viết.
    """
    if article.get("title"):
        return str(article["title"]).strip()
    for h in article.get("structure", {}).get("headings", []):
        if h.get("level") == 1 and h.get("text"):
            return str(h["text"]).strip()
    ct = article.get("cleaned_text", "")
    return ct.split("\n", 1)[0].strip() if ct else ""


def classify_title(title: str, reg: EntityRegistry | None = None) -> dict:
    """Nhận diện thực thể và ngành nghề trực tiếp từ tiêu đề bài viết.

    Args:
        title: Chuỗi tiêu đề bài viết cần phân tích.
        reg: Đối tượng EntityRegistry dùng để tra cứu (nếu None sẽ tải mặc định).

    Returns:
        Từ điển chứa danh sách thực thể phát hiện, ngành liên quan, mức độ phù hợp và cờ needs_agent.
    """
    reg = reg or load_registry()
    dets = reg.detect(title)
    ids = [d["entity_id"] for d in dets]
    types = sorted({d["type"] for d in dets})

    industries: set[str] = set()
    for d in dets:
        if d["type"] in _INDUSTRY:
            industries.add(d["canonical_name"])
        attrs = reg.entities[d["entity_id"]]["attributes"]
        for k in ("gics1", "gics2", "gics3"):
            if attrs.get(k):
                industries.add(attrs[k])

    tset = set(types)
    if _SECURITY & tset:
        relevance = "entity"
    elif _INDUSTRY & tset:
        relevance = "industry"
    elif _ASSET & tset:
        relevance = "asset"
    elif _INST & tset:
        relevance = "institution"
    elif _MACRO & tset:
        relevance = "macro"
    elif _MARKET & tset:
        relevance = "market"
    else:
        relevance = "none"

    primary = next((d["entity_id"] for d in dets if d["type"] in _SECURITY), None)
    if primary is None:
        primary = next((d["entity_id"] for d in dets if d["type"] in _INDUSTRY or d["type"] in _ASSET), None)
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
        "needs_agent": len(ids) == 0,
    }


def classify_article(article: dict, reg: EntityRegistry | None = None) -> dict:
    """Phân loại thực thể cho một đối tượng bài viết hoàn chỉnh.

    Args:
        article: Từ điển dữ liệu bài viết tầng Silver.
        reg: Đối tượng EntityRegistry dùng tra cứu.

    Returns:
        Từ điển kết quả phân loại kèm mã định danh bài viết và tên miền nguồn.
    """
    reg = reg or load_registry()
    rec = classify_title(title_of(article), reg)
    rec["article_id"] = article.get("article_id")
    rec["domain"] = article.get("domain")
    return rec
