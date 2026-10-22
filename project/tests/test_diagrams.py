"""Kiểm sơ đồ vận hành: cú pháp cơ bản, tham chiếu tệp còn tồn tại, trang HTML tự chứa."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.docs.build_diagrams import build, read_diagram

PROJECT = Path(__file__).resolve().parent.parent
REPO = PROJECT.parent
DIAGRAMS = PROJECT / "docs" / "diagrams"
MMD = sorted(DIAGRAMS.glob("*.mmd"))

KINDS = ("flowchart", "sequenceDiagram", "stateDiagram-v2")
# Tên tệp chỉ có lúc chạy (dữ liệu, packet, đầu ra) nên không tìm thấy trong repo.
RUNTIME_NAMES = {
    "agy_standing_order.yaml", "task.json", "map.json", "wave.json", "conductor.ts",
    "meta.json", "latest.json", "HANDOFF-latest.md", "SESSION-LATEST.md", "ngày.json", "ngày.xlsx",
    "ops.db", "ops_dbos.db", "monocle.db", "harness.db", "discovered_urls", "ngày.xlsx",
}
FILE_TOKEN = re.compile(r"[\w][\w./-]*\.(?:py|yaml|ts|md)\b")


@pytest.mark.parametrize("path", MMD, ids=lambda p: p.name)
def test_diagram_has_valid_kind_and_title(path):
    d = read_diagram(path)
    assert d["code"].split("\n", 1)[0].split()[0] in KINDS, "dòng đầu phải khai báo loại sơ đồ"
    assert d["title"] != path.stem and d["desc"], "thiếu %% title: hoặc %% desc:"
    assert not re.search(r"^\s*graph\s", d["code"], re.M), "dùng flowchart, không dùng graph"


@pytest.mark.parametrize("path", MMD, ids=lambda p: p.name)
def test_diagram_labels_reference_existing_files(path):
    names = {p.name for p in REPO.rglob("*") if p.suffix in (".py", ".yaml", ".ts", ".md") and ".git" not in p.parts}
    missing = []
    for tok in FILE_TOKEN.findall(read_diagram(path)["code"]):
        base = tok.rsplit("/", 1)[-1]
        if base in RUNTIME_NAMES or base in names or "*" in base:
            continue
        missing.append(tok)
    assert not missing, f"sơ đồ nêu tệp không tồn tại trong repo: {missing}"


def test_diagram_numbers_are_unique():
    prefixes = [p.name[:2] for p in MMD]
    assert len(prefixes) == len(set(prefixes))


def test_index_html_is_current_and_self_contained():
    page = (DIAGRAMS / "index.html").read_text(encoding="utf-8")
    assert page == build(), "index.html lỗi thời: chạy scripts/docs/build_diagrams.py"
    assert not re.search(r"(?:src|href)=[\"']https?://", page), "trang không được gọi tài nguyên ngoài"
    assert "@@" not in page.split("<script>", 1)[0], "còn chỗ giữ chỗ chưa thay"
    assert 'id="map"' in page and 'id="dtabs"' in page


def _template_files() -> list[str]:
    """Mọi đường dẫn nêu trong các khối `files:[...]` của mẫu bản đồ."""
    tpl = (DIAGRAMS / "map.template.html").read_text(encoding="utf-8")
    out: list[str] = []
    for block in re.findall(r"files:\[(.*?)\]", tpl, re.S):
        out += re.findall(r'"([^"]+)"', block)
    return out


REMOTE_ONLY = {"_manifest/latest.json", "users/output/"}  # nằm trên SharePoint hoặc gốc dữ liệu, không có trong repo


def test_map_nodes_reference_existing_files():
    skip = ("C:", "<", "…", "=")
    missing = []
    for ref in _template_files():
        if ref in REMOTE_ONLY:
            continue
        if ref.startswith(skip) or any(c in ref for c in "<…") or "/" not in ref and not ref.endswith((".md", ".py")):
            continue
        pattern = ref.split(" ")[0]
        hits = list(REPO.glob(pattern)) if "*" in pattern else ([REPO / pattern] if (REPO / pattern).exists() else [])
        if not hits:
            missing.append(ref)
    assert not missing, f"bản đồ nêu tệp không tồn tại: {missing}"


BANNED_PHRASES = (
    "Đáng chú ý", "Điều quan trọng", "Có thể thấy", "Nhìn chung", "Hơn nữa", "Tóm lại", "mạnh mẽ", "vượt trội",
    "đột phá", "hoàn hảo", "toàn diện", "không chỉ", "Production Ready", "seamless", "robust", "cutting-edge",
)
DECORATIVE = re.compile("[✓✗▲▼◐⚠→—\U0001F300-\U0001FAFF\u2705\u274c\u2728]")


def test_map_text_follows_report_standards():
    """No hype phrases, emoji or decorative symbols, and no dot-separated sentence fragments (STANDARD S2)."""
    tpl = (DIAGRAMS / "map.template.html").read_text(encoding="utf-8")
    assert not DECORATIVE.search(tpl), DECORATIVE.search(tpl)
    low = tpl.lower()
    assert not [p for p in BANNED_PHRASES if p.lower() in low]
    assert tpl.count(" · ") <= 3, "chỉ khối tiêu đề (dòng series và dòng ngày) được dùng dấu chấm giữa; nơi khác dùng dấu phẩy hoặc câu đầy đủ"
    assert "@media (prefers-color-scheme" not in tpl, "một giao diện sáng duy nhất (S7.2)"
    assert not re.search(r"(?:src|href)=[\"']https?://", tpl)
