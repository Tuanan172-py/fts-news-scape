"""
Tests cho classifier.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processor.classifier import classify_rule_based


def test_finance_classification():
    """Title có từ khoá chứng khoán → finance."""
    cats = classify_rule_based("VN-Index tăng mạnh phiên cuối tuần")
    assert "finance" in cats, f"Expected finance in {cats}"


def test_trading_classification():
    """Title có từ khoá trading → trading."""
    cats = classify_rule_based("Phân tích kỹ thuật VN30F1M: MA cross")
    assert "trading" in cats, f"Expected trading in {cats}"


def test_multi_category():
    """1 article có thể thuộc nhiều category."""
    cats = classify_rule_based(
        "AI và Machine Learning trong giao dịch chứng khoán"
    )
    assert "finance" in cats, f"Expected finance in {cats}"
    assert "trading" in cats or "tech" in cats, f"Expected trading/tech in {cats}"


def test_uncategorized():
    """Article không match rule nào → uncategorized."""
    cats = classify_rule_based("Công thức nấu ăn ngon mỗi ngày")
    assert "uncategorized" in cats, f"Expected uncategorized in {cats}"


def test_body_scan():
    """Classifier cũng scan body, không chỉ title."""
    cats = classify_rule_based(
        "Bài viết hàng ngày",
        body="Hôm nay thị trường chứng khoán có nhiều biến động..."
    )
    assert "finance" in cats, f"Expected finance from body scan in {cats}"


if __name__ == "__main__":
    test_finance_classification()
    test_trading_classification()
    test_multi_category()
    test_uncategorized()
    test_body_scan()
    print("All classifier tests passed!")
