"""Checks for the operations diagrams: Mermaid basics, file references, report-style rules, self-contained HTML."""

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
# File names that exist only at run time (data, packets, outputs), so the repository does not hold them.
RUNTIME_NAMES = {
    "agy_standing_order.yaml", "task.json", "map.json", "wave.json", "conductor.ts",
    "meta.json", "latest.json", "HANDOFF-latest.md", "SESSION-LATEST.md", "date.json", "date.xlsx",
    "ops.db", "ops_dbos.db", "monocle.db", "harness.db", "discovered_urls",
}
FILE_TOKEN = re.compile(r"[\w][\w./-]*\.(?:py|yaml|ts|md)\b")
VIETNAMESE = re.compile(
    "[ạảãàáâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]")


@pytest.mark.parametrize("path", MMD, ids=lambda p: p.name)
def test_diagram_has_valid_kind_and_title(path):
    d = read_diagram(path)
    assert d["code"].split("\n", 1)[0].split()[0] in KINDS, "the first line must declare the diagram kind"
    assert d["title"] != path.stem and d["desc"], "missing %% title: or %% desc:"
    assert not re.search(r"^\s*graph\s", d["code"], re.M), "use flowchart, not graph"


@pytest.mark.parametrize("path", MMD, ids=lambda p: p.name)
def test_diagram_labels_reference_existing_files(path):
    names = {p.name for p in REPO.rglob("*") if p.suffix in (".py", ".yaml", ".ts", ".md") and ".git" not in p.parts}
    missing = []
    for tok in FILE_TOKEN.findall(read_diagram(path)["code"]):
        base = tok.rsplit("/", 1)[-1]
        if base in RUNTIME_NAMES or base in names or "*" in base:
            continue
        missing.append(tok)
    assert not missing, f"the diagram names files that are not in the repository: {missing}"


@pytest.mark.parametrize("path", MMD, ids=lambda p: p.name)
def test_diagram_text_is_english(path):
    assert not VIETNAMESE.search(path.read_text(encoding="utf-8")), "diagram text must be English"


def test_diagram_numbers_are_unique():
    prefixes = [p.name[:2] for p in MMD]
    assert len(prefixes) == len(set(prefixes))


def test_index_html_is_current_and_self_contained():
    page = (DIAGRAMS / "index.html").read_text(encoding="utf-8")
    assert page == build(), "index.html is stale: run scripts/docs/build_diagrams.py"
    assert not re.search(r"(?:src|href)=[\"']https?://", page), "the page must not load external resources"
    assert "@@" not in page.split("<script>", 1)[0], "a placeholder was not replaced"
    assert 'id="map"' in page and 'id="dtabs"' in page


def _template_files() -> list[str]:
    """Return every path named in the `files:[...]` blocks of the map template."""
    tpl = (DIAGRAMS / "map.template.html").read_text(encoding="utf-8")
    out: list[str] = []
    for block in re.findall(r"files:\[(.*?)\]", tpl, re.S):
        out += re.findall(r'"([^"]+)"', block)
    return out


REMOTE_ONLY = {"_manifest/latest.json", "users/output/"}  # live on SharePoint or in the data root, not in the repo


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
    assert not missing, f"the map names files that do not exist: {missing}"


BANNED_PHRASES = (
    "moreover", "furthermore", "overall,", "in conclusion", "it is important to note", "it's important", "let's",
    "robust", "seamless", "cutting-edge", "game-changing", "revolutionize", "unlock", "leverage", "empower",
    "state-of-the-art", "next-generation", "production ready", "powerful", "comprehensive solution",
)
DECORATIVE = re.compile("[✓✗▲▼◐⚠→—\U0001F300-\U0001FAFF✅❌✨]")


def test_map_text_follows_report_standards():
    """No hype phrases, emoji, decorative symbols or Vietnamese text in the map template (STANDARD S2)."""
    tpl = (DIAGRAMS / "map.template.html").read_text(encoding="utf-8")
    assert not DECORATIVE.search(tpl), DECORATIVE.search(tpl)
    low = tpl.lower()
    assert not [p for p in BANNED_PHRASES if p in low]
    assert not VIETNAMESE.search(tpl), "the document is written in English"
    assert tpl.count(" · ") <= 3, "only the title block (series line and date line) may use the middle dot"
    assert "@media (prefers-color-scheme" not in tpl, "one light theme only (S7.2)"
    assert not re.search(r"(?:src|href)=[\"']https?://", tpl)


@pytest.mark.parametrize("path", [p for p in MMD if "sequenceDiagram" in p.read_text(encoding="utf-8")], ids=lambda p: p.name)
def test_sequence_messages_have_no_semicolon(path):
    """A semicolon ends a statement in a Mermaid sequence diagram and breaks the figure."""
    body = [ln for ln in read_diagram(path)["code"].splitlines() if not ln.strip().startswith("%%")]
    assert not [ln for ln in body if ";" in ln], "replace ';' with ',' or 'and' in sequence messages"
