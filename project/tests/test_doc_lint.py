"""Kiểm thử bộ lint chuẩn trình bày: kho sạch và từng luật bắt đúng lỗi cố ý."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import doc_lint as dl  # noqa: E402


def rules(findings):
    return {f.rule for f in findings}


def test_repo_in_scope_has_no_findings():
    assert [str(f) for f in dl.lint_repo()] == []


@pytest.mark.parametrize("text,rule", [
    ("Nhìn chung hệ thống ổn.", "L01"),
    ("Trạng thái ✅ xong.", "L02"),
    ("Cấp standing order mới.", "L03"),
    ("Xem US-031 để biết thêm.", "L04"),
    (" ".join(["từ"] * 30) + ".", "L08"),
])
def test_markdown_rules_catch_seeded_defect(text, rule):
    assert rule in rules(dl.lint_markdown("x.md", text))


def test_markdown_clean_text_passes():
    assert dl.lint_markdown("x.md", "Hệ thống chạy ổn định.") == []


def test_markdown_skips_code_fence_and_inline_code():
    text = "```\nNhìn chung US-031\n```\nDùng `US-031` khi cần."
    assert dl.lint_markdown("x.md", text) == []


def test_python_rules():
    src = 'def f():\n    """Nhìn chung."""\n    return "xong ✅"  # tôi làm\n'
    assert {"L01", "L02"} <= rules(dl.lint_python("x.py", src))
    assert rules(dl.lint_python("x.py", "def (:")) == {"L00"}


def test_html_rules():
    assert {"L02", "L04"} <= rules(dl.lint_html("x.html", "<p>Xong ✅ US-031</p>"))
    assert dl.lint_html("x.html", "<p>Đã xong.</p>") == []
