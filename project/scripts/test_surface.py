"""Kiểm thử khớp nối chuỗi bề mặt và kiểm định đầu ra tầng L1."""
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

def get_word_spans(text: str):
    """Return list of (word, start, end) in text."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[^\s,;:\.!?\"'“”‘’\(\)\[\]{}]+", text)]

def find_exact_surface_fast(title: str, query: str) -> str | None:
    """Find exact case-preserved substring in title matching query."""
    if not query or not title:
        return None
    # 1. Exact match
    if query in title:
        return query
    # 2. Case-insensitive regex match
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
    
    # Check sliding window of word count around q_len
    for length in range(q_len, min(q_len + 3, num_words + 1)):
        for i in range(num_words - length + 1):
            start_idx = spans[i][1]
            end_idx = spans[i + length - 1][2]
            slice_text = title[start_idx:end_idx]
            if _fold(slice_text) == fq:
                return slice_text
    return None

# Test finding
t_sample = "NVIDIA nổi lên như “nhà băng” cho ngành công nghiệp AI"
print("Test find:", find_exact_surface_fast(t_sample, "ngành công nghiệp"))
