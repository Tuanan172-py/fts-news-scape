"""
Classifier — phân loại nội dung article.

Rule-based (keyword, regex) — nhanh, deterministic, không cần LLM.
"""

import re

# Keyword rules — simple, fast
CATEGORY_RULES: dict[str, list[re.Pattern]] = {
    "finance": [
        re.compile(r"(VN-?Index|chứng khoán|cổ phiếu|thị trường|đầu tư|ngân hàng)", re.I),
        re.compile(r"(VN30|VN30F1M|HOSE|HNX|UPCOM)", re.I),
        re.compile(r"(lãi suất|lạm phát|GDP|CPI|trái phiếu|cổ tức)", re.I),
        re.compile(r"(SSI|VND|HCM|VCI|FPT|VCB|BID|CTG)", re.I),
    ],
    "tech": [
        re.compile(r"(AI|artificial intelligence|machine learning|deep learning)", re.I),
        re.compile(r"(LLM|GPT|Claude|Gemini|transformer)", re.I),
        re.compile(r"(Rust|Python|TypeScript|blockchain|crypto)", re.I),
        re.compile(r"(startup|funding|venture|IPO)", re.I),
    ],
    "trading": [
        re.compile(r"(giao dịch|trading|entry|exit|signal|stop loss)", re.I),
        re.compile(r"(phân tích kỹ thuật|technical analysis|chart pattern)", re.I),
        re.compile(r"(MA|RSI|MACD|Bollinger|Fibonacci|ichimoku)", re.I),
        re.compile(r"(order flow|market profile|volume profile|delta)", re.I),
    ],
    "cmt": [
        re.compile(r"(CMT|chartered market technician)", re.I),
        re.compile(r"(Elliott|Dow Theory|intermarket|relative strength)", re.I),
        re.compile(r"(momentum|sentiment|breadth|advance.decline)", re.I),
    ],
}


def classify_rule_based(title: str, body: str = "") -> list[str]:
    """Rule-based classification, trả về list categories (có thể nhiều).

    Dựa trên title + body. Nhanh, deterministic.
    """
    text = f"{title} {body[:2000]}"
    categories = []
    for cat, patterns in CATEGORY_RULES.items():
        for pat in patterns:
            if pat.search(text):
                categories.append(cat)
                break
    return categories if categories else ["uncategorized"]


# LLM-based classification: để dành phase sau (spec §9 — rule-based trước).
