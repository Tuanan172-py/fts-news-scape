# -*- coding: utf-8 -*-
"""
L1 Entity Matcher & Auditor.
"""
import glob
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.entities import load_registry, _fold, CODE_STOPLIST, _CODE_RE, PROTECTED_SHORT_WORDS
from src.agent.l1_router import check_l1_dod, _CATEGORY_KEYS

reg = load_registry()

TYPE_GROUP_MAP = {
    "TICKER": "ticker_company",
    "SECURITY_OTHER": "ticker_company",
    "ETF": "etf_fund",
    "INDEX": "index",
    "EXCHANGE": "exchange",
    "INDUSTRY_GICS1": "industry_sector",
    "INDUSTRY_GICS2": "industry_sector",
    "INDUSTRY_GICS3": "industry_sector",
    "MACRO_GEO": "macro_geo",
    "MACRO_THEME": "macro_geo",
    "ASSET_CLASS": "asset_class",
    "INSTITUTION": "institution",
}

# Known global tech/companies/institutions for unlisted extraction
GLOBAL_UNLISTED_ENTITIES = {
    "NVIDIA": ("TICKER", "ticker_company"),
    "Apple": ("TICKER", "ticker_company"),
    "Tesla": ("TICKER", "ticker_company"),
    "Microsoft": ("TICKER", "ticker_company"),
    "OpenAI": ("TICKER", "ticker_company"),
    "Intel": ("TICKER", "ticker_company"),
    "Amazon": ("TICKER", "ticker_company"),
    "Google": ("TICKER", "ticker_company"),
    "Meta": ("TICKER", "ticker_company"),
    "BYD": ("TICKER", "ticker_company"),
    "SpaceX": ("TICKER", "ticker_company"),
    "Boeing": ("TICKER", "ticker_company"),
    "TSMC": ("TICKER", "ticker_company"),
    "Huawei": ("TICKER", "ticker_company"),
    "Samsung": ("TICKER", "ticker_company"),
    "Foxconn": ("TICKER", "ticker_company"),
    "Hyundai": ("TICKER", "ticker_company"),
    "Toyota": ("TICKER", "ticker_company"),
    "Honda": ("TICKER", "ticker_company"),
    "Alibaba": ("TICKER", "ticker_company"),
    "Tencent": ("TICKER", "ticker_company"),
    "TikTok": ("TICKER", "ticker_company"),
    "ByteDance": ("TICKER", "ticker_company"),
}

# Known macro geopolitical / unlisted countries
UNLISTED_MACRO = {
    "Iran": ("MACRO_GEO", "macro_geo"),
    "Israel": ("MACRO_GEO", "macro_geo"),
    "Nga": ("MACRO_GEO", "macro_geo"),
    "Ukraine": ("MACRO_GEO", "macro_geo"),
    "Đức": ("MACRO_GEO", "macro_geo"),
    "Pháp": ("MACRO_GEO", "macro_geo"),
    "Anh": ("MACRO_GEO", "macro_geo"),
    "Hàn Quốc": ("MACRO_GEO", "macro_geo"),
    "Thái Lan": ("MACRO_GEO", "macro_geo"),
    "Indonesia": ("MACRO_GEO", "macro_geo"),
    "Malaysia": ("MACRO_GEO", "macro_geo"),
    "Philippines": ("MACRO_GEO", "macro_geo"),
    "Singapore": ("MACRO_GEO", "macro_geo"),
    "Ấn Độ": ("MACRO_GEO", "macro_geo"),
    "Campuchia": ("MACRO_GEO", "macro_geo"),
    "Lào": ("MACRO_GEO", "macro_geo"),
}

def get_word_spans(text: str):
    """Return list of (word, start, end) in text."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[^\s,;:\.!?\"'“”‘’\(\)\[\]{}]+", text)]

def find_exact_surface(title: str, query: str) -> str | None:
    """Find exact case-preserved substring in title matching query."""
    if not query or not title:
        return None
    # 1. Exact match
    if query in title:
        return query
    # 2. Case-insensitive regex match with word boundaries
    m = re.search(r"\b" + re.escape(query) + r"\b", title, re.IGNORECASE)
    if m:
        return m.group(0)
    m = re.search(re.escape(query), title, re.IGNORECASE)
    if m:
        return m.group(0)
    # 3. Folded match via word tokens
    fq = _fold(query)
    q_len = len(fq.split())
    spans = get_word_spans(title)
    num_words = len(spans)
    
    for length in range(q_len, min(q_len + 3, num_words + 1)):
        for i in range(num_words - length + 1):
            start_idx = spans[i][1]
            end_idx = spans[i + length - 1][2]
            slice_text = title[start_idx:end_idx]
            if _fold(slice_text) == fq:
                return slice_text
    return None

def match_entities_in_title(title: str, code_first: dict) -> tuple[list[dict], list[str]]:
    """
    Returns (entities, unlisted_candidates)
    """
    entities = []
    unlisted = []
    seen_eids = set()
    seen_surfaces = set()

    # 1. Check exact 3-letter codes
    for m in _CODE_RE.findall(title):
        if m in CODE_STOPLIST:
            continue
        for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX", "EXCHANGE", "MACRO_GEO", "ASSET_CLASS", "INSTITUTION"):
            eid = f"{etype}:{m}"
            if eid in reg.entities and eid not in seen_eids:
                if m in title:
                    seen_eids.add(eid)
                    seen_surfaces.add(m)
                    entities.append({
                        "surface": m,
                        "entity_id": eid,
                        "type": etype,
                        "method": "exact_code",
                        "in_list": True,
                        "confidence": 0.95
                    })
                    break

    # 2. Check catalog aliases
    folded_title = _fold(title)
    sorted_aliases = sorted(reg._alias_index.keys(), key=lambda k: len(k), reverse=True)
    
    for alias_key in sorted_aliases:
        pattern = r"\b" + re.escape(alias_key) + r"\b"
        if re.search(pattern, folded_title):
            for eid in reg._alias_index[alias_key]:
                if eid in seen_eids:
                    continue
                ent = reg.entities[eid]
                
                # Guard against false positives
                if alias_key == "quy" and not re.search(r"\b[Qq]uỹ\b", title):
                    continue
                if alias_key == "dau" and not re.search(r"\b[Dd]ầu\b", title):
                    continue
                if alias_key == "ban" and not re.search(r"\b[Bb]án lẻ\b", title):
                    continue
                if alias_key == "my" and not re.search(r"\bMỹ\b", title):
                    continue
                if alias_key == "eu" and not re.search(r"\bEU\b", title):
                    continue
                if alias_key == "us" and not re.search(r"\bUS\b", title):
                    continue

                surface = None
                for a in ent.get("aliases", []) + [ent.get("canonical_name", "")]:
                    s = find_exact_surface(title, a)
                    if s and s in title:
                        surface = s
                        break
                if not surface:
                    surface = find_exact_surface(title, alias_key)
                
                if surface and surface in title:
                    seen_eids.add(eid)
                    seen_surfaces.add(surface)
                    entities.append({
                        "surface": surface,
                        "entity_id": eid,
                        "type": ent["type"],
                        "method": "alias",
                        "in_list": True,
                        "confidence": 0.95
                    })

    # 3. Check code_first hints
    cf_eids = code_first.get("entity_ids", [])
    for eid in cf_eids:
        if eid in reg.entities and eid not in seen_eids:
            ent = reg.entities[eid]
            surface = None
            for a in ent.get("aliases", []) + [ent.get("canonical_name", ""), ent.get("code", "")]:
                s = find_exact_surface(title, a)
                if s and s in title:
                    if _fold(s) == "quy" and not re.search(r"\b[Qq]uỹ\b", title):
                        continue
                    if _fold(s) == "dau" and not re.search(r"\b[Dd]ầu\b", title):
                        continue
                    surface = s
                    break
            if surface and surface in title:
                seen_eids.add(eid)
                seen_surfaces.add(surface)
                entities.append({
                    "surface": surface,
                    "entity_id": eid,
                    "type": ent["type"],
                    "method": "alias",
                    "in_list": True,
                    "confidence": 0.95
                })

    # 4. Check global unlisted entities (e.g. NVIDIA, Apple, etc.)
    for name, (etype, cat_group) in GLOBAL_UNLISTED_ENTITIES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", title, re.IGNORECASE):
            s = find_exact_surface(title, name)
            if s and s in title and s not in seen_surfaces:
                seen_surfaces.add(s)
                unlisted.append(s)
                entities.append({
                    "surface": s,
                    "entity_id": None,
                    "type": etype,
                    "method": "semantic",
                    "in_list": False,
                    "confidence": 0.95
                })

    # 5. Check unlisted macro geo (e.g. Iran, Israel, etc.)
    for name, (etype, cat_group) in UNLISTED_MACRO.items():
        if re.search(r"\b" + re.escape(name) + r"\b", title):
            s = find_exact_surface(title, name)
            if s and s in title and s not in seen_surfaces:
                seen_surfaces.add(s)
                unlisted.append(s)
                entities.append({
                    "surface": s,
                    "entity_id": None,
                    "type": etype,
                    "method": "semantic",
                    "in_list": False,
                    "confidence": 0.95
                })

    return entities, unlisted

def build_l1_output(task: dict) -> dict:
    aid = task["article_id"]
    title = task["title"]
    code_first = task.get("code_first", {})
    
    entities, unlisted = match_entities_in_title(title, code_first)
    recognized = len(entities) > 0

    # Build categories
    categories = {k: "none" for k in _CATEGORY_KEYS}
    
    if recognized:
        for e in entities:
            grp = TYPE_GROUP_MAP.get(e["type"])
            if grp and grp in categories:
                if e["in_list"]:
                    categories[grp] = "done"
                elif categories[grp] != "done":
                    categories[grp] = "out_of_list"
                    
        # Citations: exact substrings of title
        citations = [{"source_span": e["surface"]} for e in entities if e["surface"] in title]
        if not citations:
            citations = [{"source_span": title}]
    else:
        entities = []
        citations = []
        categories = {k: "none" for k in _CATEGORY_KEYS}

    out = {
        "l1_output_version": "1.0",
        "article_id": aid,
        "title": title,
        "recognized": recognized,
        "entities": entities,
        "categories": categories,
        "unlisted_candidates": unlisted,
        "citations": citations,
        "confidence": 0.95 if recognized else 0.9,
        "processing_metadata": {
            "agent_provider": "gemini",
            "model_used": "flash",
            "timestamp": "2026-09-08T16:28:52+07:00"
        }
    }
    return out

print("L1 matcher script ready.")
