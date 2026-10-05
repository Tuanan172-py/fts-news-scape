"""
Tests cho SentimentEngine — unit cases + accuracy gate ≥70% trên validation set.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.processor.sentiment import SentimentEngine

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def engine():
    return SentimentEngine(lexicon_dir=str(ROOT / "data" / "lexicon"))


def test_positive_finance_phrase(engine):
    label, score = engine.analyze("TNG lãi kỷ lục 392 tỷ trong năm 2025")
    assert label == "positive" and score > 0


def test_negative_finance_phrase(engine):
    label, score = engine.analyze("Sabeco bị xử phạt và truy thu thuế 7.5 tỷ đồng")
    assert label == "negative" and score < 0


def test_negation_flips(engine):
    pos_label, pos_score = engine.analyze("Cổ phiếu tăng")
    neg_label, neg_score = engine.analyze("Cổ phiếu không tăng")
    assert pos_score > 0
    assert neg_score < pos_score
    assert neg_label != "positive"


def test_empty_text_neutral(engine):
    assert engine.analyze("") == ("neutral", 0.0)


def test_no_sentiment_words_neutral(engine):
    label, _ = engine.analyze("VPH có Tổng Giám đốc mới")
    assert label == "neutral"


def test_finance_overrides_general(engine):
    # "tăng trần" (finance 1.0) mạnh hơn "tăng" đơn lẻ (0.5)
    _, trần_score = engine.analyze("Cổ phiếu tăng trần")
    _, tăng_score = engine.analyze("Cổ phiếu tăng")
    assert trần_score > tăng_score


def test_accuracy_on_validation_set(engine):
    path = ROOT / "data" / "labeled" / "sentiment_validation.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 50
    correct = sum(1 for r in rows
                  if engine.analyze(r["text"])[0] == r["label"])
    accuracy = correct / len(rows)
    print(f"\nsentiment validation accuracy: {accuracy:.0%} ({correct}/{len(rows)})")
    assert accuracy >= 0.70, f"accuracy {accuracy:.0%} < 70% gate"
