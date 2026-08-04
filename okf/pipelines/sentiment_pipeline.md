---
type: Python Pipeline
title: Sentiment Analysis Pipeline
description: Pipeline phân tích cảm xúc tiếng Việt rule-based — pyvi segment → n-gram lexicon match → negation flip → scoring.
resource: project/src/processor/sentiment.py
tags: [pipeline, sentiment, nlp, vietnamese, classification]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: sentiment
    resource: project/src/processor/sentiment.py
    title: Sentiment engine implementation
  - id: classifier
    resource: project/src/processor/classifier.py
    title: Rule-based classifier
  - id: sentiment-design
    resource: project/docs/design/04-sentiment-classification.md
    title: Sentiment Classification Design
sources_last_checked: 2026-08-04
---

Pipeline Sentiment Analysis là hệ thống phân tích cảm xúc **rule-based** (không dùng LLM/Machine Learning), được thiết kế riêng cho tiếng Việt trong lĩnh vực chứng khoán.[^sentiment-design]

# Kiến trúc Pipeline

```
Article (title + body)
    │
    ▼
┌─────────────────────┐
│ 1. CLASSIFY         │ ← classifier.py (rule-based keyword matching)
│ 4 categories:       │
│ finance/tech/       │
│ trading/cmt         │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 2. SEGMENT          │ ← segment.py (pyvi tokenization)
│ Tách từ tiếng Việt  │    "thị_trường tăng_điểm"
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 3. SCORE            │ ← sentiment.py (n-gram lexicon)
│ Match lexicon:      │
│ trigram > bigram    │
│ > unigram           │
│ (longest first)     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 4. NEGATION FLIP    │
│ không_tốt → -score  │
│ Không: không, chưa, │
│ chẳng, chưa_thể...  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 5. OUTPUT           │
│ mean score ± 0.2    │
│ → positive/negative │
│ /neutral            │
└─────────────────────┘
```

# Phân loại Chủ đề (Classifier)

Rule-based keyword matching, tìm trong title + 2000 ký tự đầu của body:[^classifier]

| Category | Keywords mẫu |
|---|---|
| `finance` | VN-Index, chứng khoán, cổ phiếu, HOSE, HNX, lãi suất, lạm phát, GDP... |
| `tech` | AI, machine learning, blockchain, crypto, startup, IPO... |
| `trading` | giao dịch, RSI, MACD, Bollinger, Fibonacci, stop loss... |
| `cmt` | Elliott, Dow Theory, intermarket, momentum, breadth... |

Một article có thể có nhiều category. Mặc định: `["uncategorized"]`.

# Sentiment Scoring

**Lexicon:**
- `data/lexicon/vswn_polarity.tsv` — Từ điển cảm xúc tiếng Việt tổng quát
- `data/lexicon/finance_terms.tsv` — Từ điển thuật ngữ tài chính (override từ điển tổng quát)

**Cơ chế chấm điểm:**
1. Tokenize bằng pyvi
2. Match n-gram: ưu tiên match dài nhất (trigram > bigram > unigram)
3. Áp dụng negation flip: `không tốt` → đảo dấu score
4. Title weight = 2x body weight (tỷ lệ 0.67/0.33)
5. Mean score → threshold ±0.2 để phân loại positive/negative/neutral

**English bypass:** Bài báo tiếng Anh được gán `neutral` / 0.0, không qua sentiment engine.[^sentiment]

# Hiệu suất

| Chỉ số | Mô tả |
|---|---|
| Deterministic | Cùng input → cùng output (không có randomness) |
| Không LLM | Không phụ thuộc API, không chi phí inference |
| Lexicon size | ~5000 từ (VSVN) + ~200 từ (Finance) |

# Quan hệ

- Được gọi bởi [Orchestrator](ingestion_scheduler.md) sau bước classify
- Ghi kết quả vào [articles.sentiment](../tables/articles.md) và [articles.sentiment_score](../tables/articles.md)

[^sentiment]: [Sentiment engine](project/src/processor/sentiment.py)
[^classifier]: [Rule-based classifier](project/src/processor/classifier.py)
[^sentiment-design]: [Sentiment Classification Design](project/docs/design/04-sentiment-classification.md)
