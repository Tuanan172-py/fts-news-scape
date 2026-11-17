"""Validate, allocate, index and sync governed knowledge documents under the ADR-0021 contract."""

from __future__ import annotations

import ast
import difflib
import functools
import io
import os
import re
import sqlite3
import subprocess
import tokenize
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = "docs/knowledge/schema.yaml"
LEGACY_PATH = "docs/knowledge/legacy.txt"
INDEX_PATH = "docs/INDEX.md"
TEMPLATE_DIR = "docs/templates"

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
_H2_RE = re.compile(r"^##\s+(?:\d+(?:\.\d+)*\.?\s+)?(.+?)\s*$")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u23F8\u23F9\u25AB\u25D0\u2705\u274C\u26A0\u2713\u2717]|\ufe0f")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}")
_LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")
_NUM_IN_ID_RE = re.compile(r"(\d+)$")
_INTERNAL_CODE_RE = re.compile(r"\bUS-(?!IMP\b)[A-Z0-9]+\b|\bD-[A-E]\b|\bK\d{2}\b")

_BLACKLIST_DEFAULT_VI = (
    "nhìn chung", "thông thường", "nói chung", "về cơ bản", "đáng chú ý",
    "cần lưu ý rằng", "đóng vai trò quan trọng", "toàn diện", "mạnh mẽ",
    "hiệu quả cao", "tối ưu nhất", "chúng ta", "tôi", "bạn có thể thấy rằng"
)
_BLACKLIST_DEFAULT_VI_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(w) for w in _BLACKLIST_DEFAULT_VI) + r")(?!\w)",
    re.IGNORECASE
)
_LEGACY_TERMS_DOCLINT = (("standing order", "mandate"), ("control room", "Phòng điều khiển"))
_EMOJI_ALLOW = ("_BATCH_LINE", "(✅|⚠️)")
_LEGACY_ALLOW = ("agy_standing_order", "Tên cũ")


@dataclass
class Finding:
    """One contract or presentation violation.

    Attributes:
        code: Rule code, K00 to K22 (or L00 to L08 for presentation checks).
        path: Repo-relative POSIX path.
        message: Description of the violation.
        severity: 'error' (blocking) or 'warning' (transitional).
        line: 1-based line number; 0 when the violation is at file level.
    """

    code: str
    path: str
    message: str = ""
    severity: str = "error"
    line: int = 0

    def __init__(self, code_or_rule: str, path: str, *args: Any, severity: str = "error", line: int = 0) -> None:
        self.code = code_or_rule
        self.path = path
        self.severity = severity
        if len(args) == 1:
            self.message = str(args[0])
            self.line = line
        elif len(args) == 2:
            self.line = int(args[0])
            self.message = str(args[1])
        elif len(args) == 0:
            self.message = ""
            self.line = line
        else:
            raise TypeError(f"Invalid Finding arguments: {args}")

    @property
    def rule(self) -> str:
        """Alias for code to support legacy doc_lint interface."""
        return self.code

    def __str__(self) -> str:
        level = "WARN" if self.severity == "warning" else "ERROR"
        line_str = f":{self.line}" if self.line else ""
        return f"[{level}] {self.path}{line_str} {self.code} {self.message}"


@dataclass
class Doc:
    """A governed document parsed from disk.

    Attributes:
        path: Repo-relative POSIX path.
        dtype: Document type inferred from the path glob.
        meta: Frontmatter mapping, empty when the file has none.
        body: Text after the frontmatter.
        has_frontmatter: True when a YAML frontmatter block was found.
        error: YAML parse error, if any.
        body_offset: Number of file lines before the body.
        sections: Mapping of H2 heading text to section text.
        section_order: H2 headings in document order.
    """

    path: str
    dtype: str
    meta: dict[str, Any]
    body: str
    has_frontmatter: bool
    error: str = ""
    body_offset: int = 0
    sections: dict[str, str] = field(default_factory=dict)
    section_order: list[str] = field(default_factory=list)


def load_schema(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load the knowledge contract.

    Args:
        root: Repository root.

    Returns:
        Parsed schema mapping.
    """
    return yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))


def as_list(value: Any) -> list[Any]:
    """Return a frontmatter value as a list.

    Args:
        value: Scalar, list or None.

    Returns:
        The value wrapped in a list, the list itself, or an empty list.
    """
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def split_sections(body: str) -> tuple[dict[str, str], list[str]]:
    """Split a markdown body into H2 sections, ignoring headings inside fenced blocks.

    Args:
        body: Markdown text without frontmatter.

    Returns:
        Mapping of heading text to section text, and headings in document order.
    """
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else _H2_RE.match(line)
        if m:
            current = m.group(1).strip()
            order.append(current)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}, order


def parse_doc(path: Path, root: Path, dtype: str) -> Doc:
    """Read one document and parse frontmatter and sections.

    Args:
        path: Absolute file path.
        root: Repository root.
        dtype: Document type the path belongs to.

    Returns:
        Parsed document.
    """
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root).as_posix()
    m = _FRONTMATTER_RE.match(text)
    meta: dict[str, Any] = {}
    error = ""
    body = text
    if m:
        body = text[m.end():]
        try:
            loaded = yaml.safe_load(m.group(1))
            meta = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError as exc:
            error = str(exc).splitlines()[0]
    has_fm = bool(m) and ("type" in meta or dtype == "skill")
    offset = text[:m.end()].count("\n") if m else 0
    doc = Doc(rel, dtype, meta, body, has_fm, error, offset)
    # Template guidance lives in HTML comments and must not count toward content floors.
    doc.sections, doc.section_order = split_sections(re.sub(r"<!--.*?-->", "", body, flags=re.S))
    return doc


@functools.lru_cache(maxsize=512)
def _glob_to_regex(pat: str) -> re.Pattern:
    """Compile a posix glob pattern with globstar (**) support to a regular expression.

    Args:
        pat: Glob pattern string.

    Returns:
        Compiled regex pattern anchored to the full path string.
    """
    pat = pat.replace("\\", "/")
    if pat.startswith("./"):
        pat = pat[2:]
    res = []
    i = 0
    n = len(pat)
    while i < n:
        if pat[i:i+4] == "/**/":
            res.append("/(?:.+/)?")
            i += 4
        elif pat[i:i+3] == "**/":
            res.append("(?:.*/)?")
            i += 3
        elif pat[i:i+3] == "/**":
            res.append("/.*")
            i += 3
        elif pat[i:i+2] == "**":
            res.append(".*")
            i += 2
        elif pat[i] == "*":
            res.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            res.append("[^/]")
            i += 1
        else:
            res.append(re.escape(pat[i]))
            i += 1
    return re.compile("^" + "".join(res) + "$")


def glob_match(path_str: str, pattern: str) -> bool:
    """Return True if path matches glob pattern with globstar (**) support.

    Args:
        path_str: Repo-relative path string.
        pattern: Posix glob pattern supporting **.

    Returns:
        True if path matches.
    """
    norm_path = str(path_str).replace("\\", "/")
    if norm_path.startswith("./"):
        norm_path = norm_path[2:]
    norm_path = norm_path.lstrip("/")
    return bool(_glob_to_regex(pattern).match(norm_path))


def is_excluded(rel: str, schema: dict[str, Any] | list[str]) -> bool:
    """Return True if a repo-relative path matches any schema-level exclude pattern.

    Args:
        rel: Repo-relative path.
        schema: Loaded schema dictionary or list of exclude patterns.

    Returns:
        True if the path is excluded from discovery and governance.
    """
    if isinstance(schema, list):
        patterns = schema
    elif isinstance(schema, dict):
        patterns = schema.get("exclude", [])
    else:
        patterns = []
    return any(glob_match(rel, pat) for pat in patterns)


def match_path(rel: str, pattern: str) -> bool:
    """Return True if repo-relative path matches glob pattern with globstar support.

    Args:
        rel: Repo-relative path.
        pattern: Posix glob pattern.

    Returns:
        True if path matches.
    """
    return glob_match(rel, pattern)


def classify_doc(rel: str, schema: dict[str, Any]) -> str | None:
    """Return the document type whose glob matches a repo-relative path under Schema v2.

    Args:
        rel: Repo-relative path.
        schema: Loaded schema dictionary.

    Returns:
        Matching type name, or None if unmanaged/excluded.
    """
    if is_excluded(rel, schema):
        return None
    for name, spec in schema.get("types", {}).items():
        type_excludes = spec.get("exclude", [])
        if any(glob_match(rel, pat) for pat in type_excludes):
            continue
        globs = spec.get("path_globs") or as_list(spec.get("path_glob"))
        for glob_pat in globs:
            if glob_match(rel, glob_pat):
                return name
    return None


_type_for_path = classify_doc


def iter_governed_files(root: Path = REPO_ROOT, schema: dict[str, Any] | None = None) -> list[tuple[Path, str]]:
    """Iterate over all files governed by Schema v2 types, returning (path, dtype).

    Args:
        root: Repository root.
        schema: Loaded schema dictionary.

    Returns:
        List of (Path, dtype) pairs.
    """
    schema = schema or load_schema(root)
    governed: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for name, spec in schema.get("types", {}).items():
        globs = spec.get("path_globs") or as_list(spec.get("path_glob"))
        type_excludes = spec.get("exclude", [])
        for glob_pat in globs:
            for p in sorted(root.glob(glob_pat)):
                if not (p.is_file() and p.suffix == ".md"):
                    continue
                rel = p.relative_to(root).as_posix()
                if rel in seen:
                    continue
                if is_excluded(rel, schema):
                    continue
                if any(glob_match(rel, pat) for pat in type_excludes):
                    continue
                seen.add(rel)
                governed.append((p, name))
    return governed


def discover(root: Path = REPO_ROOT, schema: dict[str, Any] | None = None) -> list[Doc]:
    """Collect every file that falls under a governed path glob.

    Args:
        root: Repository root.
        schema: Loaded schema; loaded from disk when omitted.

    Returns:
        Parsed documents sorted by path.
    """
    schema = schema or load_schema(root)
    governed = iter_governed_files(root, schema)
    docs = [parse_doc(p, root, dtype) for p, dtype in governed]
    return sorted(docs, key=lambda d: d.path)


def load_legacy(root: Path = REPO_ROOT) -> set[str]:
    """Read the list of files allowed to stay without frontmatter during migration.

    Args:
        root: Repository root.

    Returns:
        Set of repo-relative paths.
    """
    p = root / LEGACY_PATH
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def legacy_files(legacy: set[str]) -> set[str]:
    """Return only the file paths of a legacy list, without declared ids."""
    return {p for p in legacy if not p.startswith("id:")}


def _declared_ids(legacy: set[str]) -> set[str]:
    """Return ids declared as `id:<ID>` in legacy.txt: registered work without a file yet."""
    return {p[3:].strip() for p in legacy if p.startswith("id:")}


def _prose_lines(text: str) -> list[str]:
    """Return lines outside fenced blocks, with inline code removed."""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(re.sub(r"`[^`]*`", " ", line))
    return out


def _word_count(text: str) -> int:
    return sum(len(re.sub(r"[|*_>#\[\]()]", " ", ln).split()) for ln in _prose_lines(text))


def _table_rows(text: str) -> int:
    rows = [ln for ln in _prose_lines(text) if ln.strip().startswith("|")]
    data = [r for r in rows if not _TABLE_SEP_RE.match(r.strip())]
    return max(0, len(data) - 1)


def _list_items(text: str) -> int:
    return sum(1 for ln in _prose_lines(text) if _LIST_RE.match(ln))


def _check_language(doc: Doc, schema: dict[str, Any]) -> list[Finding]:
    """Flag Vietnamese prose in an English body and style violations (K09, K10)."""
    out: list[Finding] = []
    lang_spec = schema.get("language", {}).get("en", {})
    vi = set(lang_spec.get("vi_chars", ""))
    banned = [b.lower() for b in lang_spec.get("banned_phrases", [])]
    max_words = lang_spec.get("max_sentence_words", 35)
    english = doc.meta.get("lang") == "en"
    offset = doc.body_offset
    in_fence = False
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if english and _EMOJI_RE.search(raw):
            out.append(Finding("K10", doc.path, f"line {no}: emoji or decorative symbol", line=no))
        if not english:
            continue
        line = re.sub(r"`[^`]*`", " ", raw)
        if line.lstrip().startswith(">"):
            continue
        unquoted = re.sub(r"\"[^\"]*\"|“[^”]*”|'[^']*'", " ", line)
        if any(ch in vi for ch in unquoted):
            out.append(Finding("K09", doc.path,
                               f"line {no}: Vietnamese text in a lang: en body; quote it or translate", line=no))
        low = line.lower()
        for phrase in banned:
            if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", low):
                out.append(Finding("K10", doc.path, f"line {no}: banned phrase \"{phrase}\"", line=no))
        stripped = line.strip()
        if stripped and not stripped.startswith(("|", "#", "<!--")):
            prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
            for sentence in re.split(r"(?<=[.!?])\s+", prose):
                if len(sentence.split()) > max_words:
                    out.append(Finding("K10", doc.path,
                                       f"line {no}: sentence of {len(sentence.split())} words, max {max_words}", line=no))
                    break
    return out


def _check_k16(doc: Doc, schema: dict[str, Any]) -> list[Finding]:
    """Ensure document audience and language match ADR-0021 / ADR-0029 contract (K16)."""
    spec = schema.get("types", {}).get(doc.dtype, {})
    aud = doc.meta.get("audience") or spec.get("audience")
    if isinstance(aud, list):
        if not doc.meta.get("audience"):
            return []
        aud = doc.meta.get("audience")
    lang = doc.meta.get("lang")
    out = []
    if aud == "agent" and lang != "en":
        out.append(Finding("K16", doc.path, f"audience '{aud}' requires lang: en, found '{lang}'"))
    elif aud == "user" and lang != "vi":
        out.append(Finding("K16", doc.path, f"audience '{aud}' requires lang: vi, found '{lang}'"))
    elif aud == "operator" and lang not in ("en", "vi"):
        out.append(Finding("K16", doc.path, f"audience '{aud}' requires lang: en or vi, found '{lang}'"))
    return out


def _check_k17(doc: Doc) -> list[Finding]:
    """Enforce <= 15 lines and canonical markdown link for status: pointer (K17)."""
    if doc.meta.get("status") != "pointer":
        return []
    out = []
    prose_lines = [ln for ln in doc.body.splitlines() if ln.strip() and not ln.strip().startswith("<!--")]
    if len(prose_lines) > 15:
        out.append(Finding("K17", doc.path, f"pointer document exceeds 15 lines (found {len(prose_lines)})"))
    links = re.findall(r"\]\(([^)]+)\)", doc.body)
    if not any(not l.strip().startswith("#") for l in links):
        out.append(Finding("K17", doc.path, "pointer document must contain a markdown link to canonical target"))
    return out


def _check_k18(docs: list[Doc], schema: dict[str, Any]) -> list[Finding]:
    """Enforce single canonical document ownership for recurring topics (K18)."""
    valid_topics = set(schema.get("control", {}).get("topics", []))
    topic_owners: dict[str, list[str]] = {}
    out = []
    for d in docs:
        if d.meta.get("status") not in ("active", "accepted"):
            continue
        topics = as_list(d.meta.get("canonical_for"))
        for t in topics:
            t_str = str(t)
            if t_str not in valid_topics:
                out.append(Finding("K18", d.path, f"topic '{t_str}' not in control.topics {sorted(valid_topics)}"))
            topic_owners.setdefault(t_str, []).append(d.path)
    for topic, paths in topic_owners.items():
        if len(paths) > 1:
            for p in paths:
                out.append(Finding("K18", p, f"multiple canonical documents for topic '{topic}': {paths}"))
    return out


def _check_k19(doc: Doc, schema: dict[str, Any]) -> list[Finding]:
    """Check for deprecated terms in active documents (K19)."""
    if doc.meta.get("status") in ("retired", "deprecated", "superseded", "archived"):
        return []
    retired = schema.get("control", {}).get("retired_terms", [])
    if not retired:
        return []
    out = []
    in_fence = False
    offset = doc.body_offset
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if "Tên cũ:" in raw or "agy_standing_order" in raw:
            continue
        line_no_code = re.sub(r"`[^`]*`", " ", raw)
        prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line_no_code)
        low = prose.lower()
        for item in retired:
            term = item["term"]
            term_low = term.lower()
            pattern = r"(?<!\w)" + re.escape(term_low) + r"(?!\w)" if re.match(r"^\w", term_low) else re.escape(term_low)
            if re.search(pattern, low):
                repl = item.get("replacement", "")
                reason = item.get("reason", "")
                out.append(Finding("K19", doc.path, f"line {no}: retired term '{term}' used; replace with '{repl}' ({reason})", line=no))
    return out


def _check_k20(doc: Doc) -> list[Finding]:
    """Check that internal tracking codes do not leak to reader-facing documents (K20)."""
    if doc.meta.get("audience") != "user":
        return []
    out = []
    in_fence = False
    offset = doc.body_offset
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`", " ", raw)
        prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        m = _INTERNAL_CODE_RE.search(prose)
        if m:
            out.append(Finding("K20", doc.path, f"line {no}: internal code '{m.group(0)}' exposed in reader-facing document", line=no))
    return out


def _check_k21(doc: Doc, schema: dict[str, Any]) -> list[Finding]:
    """Check Vietnamese presentation standard: emoji, banned phrases, sentence length (K21)."""
    if doc.meta.get("lang") != "vi":
        return []
    lang_vi = schema.get("language", {}).get("vi", {})
    banned = [b.lower() for b in lang_vi.get("banned_phrases", [])]
    max_words = lang_vi.get("max_sentence_words", 25)
    out = []
    in_fence = False
    offset = doc.body_offset
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _EMOJI_RE.search(raw):
            out.append(Finding("K21", doc.path, f"line {no}: có emoji hoặc biểu tượng trang trí", line=no))
        line = re.sub(r"`[^`]*`", " ", raw)
        prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        prose_clean = re.sub(r"[*_>#]", "", prose)
        low = prose_clean.lower()
        for phrase in banned:
            pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
            m = re.search(pattern, low)
            if m:
                matched_word = prose_clean[m.start():m.end()]
                out.append(Finding("K21", doc.path, f"line {no}: từ cấm \"{matched_word}\" trong tiếng Việt", line=no))
        stripped = line.strip()
        if stripped and not stripped.startswith(("|", "#", "---", "<!--")):
            for sentence in re.split(r"(?<=[.!?])\s+", prose_clean):
                words = len(sentence.split())
                if words > max_words:
                    out.append(Finding("K21", doc.path, f"line {no}: câu {words} từ, tối đa {max_words} từ", line=no))
                    break
    return out


def _check_k22(doc: Doc, root: Path) -> list[Finding]:
    """Report relative markdown links that point to non-existent files on disk (K22)."""
    out = []
    base = (root / doc.path).parent
    in_fence = False
    offset = doc.body_offset
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`", " ", raw)
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            rel = target.split("#", 1)[0]
            if rel and not (base / rel).exists():
                out.append(Finding("K22", doc.path, f"line {no}: broken relative link '{target}'", line=no))
    return out


def _check_k14(root: Path, schema: dict[str, Any], docs: list[Doc]) -> list[Finding]:
    """Every tracked markdown file in git must belong to schema v2 or be in exempt (K14)."""
    res = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "*.md"], cwd=root, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    if res.returncode != 0:
        return []
    tracked = {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}
    governed_paths = {d.path for d in docs if d.has_frontmatter}
    exempt_paths = {entry["path"] if isinstance(entry, dict) else str(entry)
                    for entry in schema.get("exempt", [])}
    excluded_patterns = schema.get("exclude", [])
    out = []
    for rel in sorted(tracked):
        if any(glob_match(rel, pat) for pat in excluded_patterns):
            continue
        if rel not in governed_paths and rel not in exempt_paths:
            out.append(Finding("K14", rel, "unmanaged markdown file; must declare frontmatter under schema v2 or be registered in exempt"))
    return out


def _check_k15(root: Path, schema: dict[str, Any]) -> list[Finding]:
    """Every exempt entry must exist on disk and have a non-empty rationale (K15)."""
    exempt_entries = schema.get("exempt", [])
    out = []
    for entry in exempt_entries:
        if isinstance(entry, dict):
            path_str = entry.get("path", "")
            rationale = entry.get("rationale", "")
        else:
            path_str, rationale = str(entry), ""
        if not path_str or not (root / path_str).is_file():
            out.append(Finding("K15", path_str or "docs/knowledge/schema.yaml",
                               f"exempt entry '{path_str}' does not exist on disk"))
        elif not rationale or len(rationale.strip()) < 5:
            out.append(Finding("K15", path_str,
                               f"exempt entry '{path_str}' lacks required non-empty rationale"))
    return out


def _expected_stem(doc: Doc, spec: dict[str, Any]) -> str | None:
    """Return the filename prefix the id dictates, or None when not derivable."""
    did = str(doc.meta.get("id", ""))
    if doc.dtype == "adr":
        return did.replace("ADR-", "") + "-"
    if doc.dtype == "story":
        return did + "-"
    if doc.dtype == "rule":
        return did.replace("RULE-", "") + "-"
    if doc.dtype in ("fact", "runbook", "reference", "ledger", "okf"):
        return did.split("-", 1)[1] + ".md" if "-" in did else None
    if doc.dtype == "proposal":
        return did.replace("PRP-", "", 1) + ".md"
    if doc.dtype == "run":
        return did.replace("RUN-", "", 1) + ".md"
    if doc.dtype == "plan":
        return did.replace("PLN-", "", 1)
    return None


def _check_doc(doc: Doc, schema: dict[str, Any], root: Path = REPO_ROOT) -> list[Finding]:
    """Validate one document that has frontmatter against its type spec."""
    out: list[Finding] = []
    spec = schema["types"][doc.dtype]
    common = schema["common"]
    meta = doc.meta

    if spec.get("external_schema"):
        for key in spec.get("required", []):
            if key not in meta or meta[key] in (None, "", []):
                out.append(Finding("K01", doc.path, f"missing required key '{key}'"))
        return out

    if meta.get("type") != doc.dtype:
        out.append(Finding("K03", doc.path, f"type is '{meta.get('type')}', path requires '{doc.dtype}'"))
    for key in common["required"] + spec.get("required", []):
        if key != "outcome_link" and (key not in meta or meta[key] in (None, "", [])):
            out.append(Finding("K01", doc.path, f"missing required key '{key}'"))
    status = meta.get("status")
    for key in spec.get("required_when", {}).get(status, []):
        if key == "outcome_link":
            if not any(as_list(meta.get(k)) for k in ("adr", "story", "plan")):
                out.append(Finding("K01", doc.path, "decided proposal needs an adr, story or plan link"))
        elif not as_list(meta.get(key)):
            out.append(Finding("K01", doc.path, f"status '{status}' requires key '{key}'"))
    known = set(common["required"]) | set(common["optional"])
    for key in meta:
        if key not in known:
            out.append(Finding("K01", doc.path, f"unknown key '{key}'; see {SCHEMA_PATH}"))
    if status not in spec["statuses"]:
        out.append(Finding("K02", doc.path, f"status '{status}' not in {spec['statuses']}"))
    for key, allowed in common["enums"].items():
        if key in meta:
            val = meta[key]
            if isinstance(val, list):
                for v in val:
                    if v not in allowed:
                        out.append(Finding("K02", doc.path, f"{key} '{v}' not in {allowed}"))
            elif val not in allowed:
                out.append(Finding("K02", doc.path, f"{key} '{val}' not in {allowed}"))
    if meta.get("lang") not in spec["lang"]:
        out.append(Finding("K02", doc.path, f"lang '{meta.get('lang')}' not in {spec['lang']}"))
    did = str(meta.get("id", ""))
    if not re.match(spec["id_pattern"], did):
        out.append(Finding("K03", doc.path, f"id '{did}' does not match {spec['id_pattern']}"))
    else:
        stem = _expected_stem(doc, spec)
        rel_name = doc.path.split("/")[-2] if doc.dtype == "plan" else doc.path.split("/")[-1]
        if stem and not (rel_name.lower() == stem.lower() or rel_name.lower().startswith(stem.lower())):
            out.append(Finding("K03", doc.path, f"file name must start with '{stem}' for id {did}"))
    for key in common["date_keys"]:
        if key in meta and not isinstance(meta[key], (date, datetime)):
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(meta[key])):
                out.append(Finding("K12", doc.path, f"{key} '{meta[key]}' is not YYYY-MM-DD"))
    for ev in as_list(meta.get("evidence")):
        if not any(str(ev).startswith(p) for p in common["evidence_prefixes"]):
            out.append(Finding("K08", doc.path, f"evidence '{ev}' lacks a prefix {common['evidence_prefixes']}"))
    summary = str(meta.get("summary", ""))
    if summary and len(summary.split()) > 40:
        out.append(Finding("K06", doc.path, "summary longer than 40 words"))
    positions = []
    for sec in spec.get("sections", []):
        if sec not in doc.sections:
            out.append(Finding("K05", doc.path, f"missing section '## {sec}'"))
        else:
            positions.append(doc.section_order.index(sec))
    if positions != sorted(positions):
        out.append(Finding("K05", doc.path, f"sections out of order; expected {spec['sections']}"))
    for sec, floor in spec.get("floors", {}).items():
        text = doc.sections.get(sec)
        if text is None:
            continue
        if _word_count(text) < floor.get("min_words", 0):
            out.append(Finding("K06", doc.path, f"section '{sec}' under {floor['min_words']} words"))
        if _table_rows(text) < floor.get("min_table_rows", 0):
            out.append(Finding("K06", doc.path, f"section '{sec}' needs {floor['min_table_rows']}+ table rows"))
        if _list_items(text) < floor.get("min_list_items", 0):
            out.append(Finding("K06", doc.path, f"section '{sec}' needs {floor['min_list_items']}+ list items"))
    out += _check_language(doc, schema)
    out += _check_k16(doc, schema)
    out += _check_k17(doc)
    out += _check_k19(doc, schema)
    out += _check_k20(doc)
    out += _check_k21(doc, schema)
    out += _check_k22(doc, root)
    return out


def reverse_links(docs: list[Doc]) -> dict[str, dict[str, set[str]]]:
    """Compute inbound supersedes and amends edges for every id.

    Args:
        docs: Documents with frontmatter.

    Returns:
        Mapping id -> {"superseded_by": ids, "amended_by": ids}.
    """
    rev: dict[str, dict[str, set[str]]] = {}
    for d in docs:
        did = str(d.meta.get("id"))
        rev.setdefault(did, {"superseded_by": set(), "amended_by": set()})
        for t in as_list(d.meta.get("supersedes")):
            rev.setdefault(str(t), {"superseded_by": set(), "amended_by": set()})["superseded_by"].add(did)
        for t in as_list(d.meta.get("amends")):
            rev.setdefault(str(t), {"superseded_by": set(), "amended_by": set()})["amended_by"].add(did)
        for t in as_list(d.meta.get("superseded_by")):
            rev[did]["superseded_by"].add(str(t))
        for t in as_list(d.meta.get("amended_by")):
            rev[did]["amended_by"].add(str(t))
    return rev


def lint(root: Path = REPO_ROOT, only: set[str] | None = None) -> list[Finding]:
    """Validate every governed document, or report only for a subset of paths.

    Cross-document checks (duplicate ids, link targets, supersession, canonical topics,
    tracked files classification, exempt integrity) always load the full corpus.

    Args:
        root: Repository root.
        only: Repo-relative paths to report on; None reports on everything.

    Returns:
        Findings sorted by path and code.
    """
    schema = load_schema(root)
    docs = discover(root, schema)
    legacy = load_legacy(root)
    out: list[Finding] = []
    governed = []
    for d in docs:
        if d.error:
            out.append(Finding("K01", d.path, f"frontmatter is not valid YAML: {d.error}"))
            continue
        if not d.has_frontmatter:
            if (d.dtype in ("adr", "story", "proposal", "plan", "fact", "rule", "run")
                    and not schema["types"][d.dtype].get("opt_in")):
                if d.path not in legacy:
                    out.append(Finding("K00", d.path, "no frontmatter; create with `harness_cli.py doc new`"))
            continue
        governed.append(d)
        out += _check_doc(d, schema, root)
    ids: dict[str, str] = {}
    for d in governed:
        spec = schema["types"].get(d.dtype, {})
        if spec.get("external_schema"):
            continue
        did = str(d.meta.get("id") or "")
        if did and did != "None":
            if did in ids:
                out.append(Finding("K04", d.path, f"duplicate id {did}, also in {ids[did]}"))
            ids.setdefault(did, d.path)
    known = set(ids) | _legacy_ids(legacy)
    for d in governed:
        spec = schema["types"].get(d.dtype, {})
        if spec.get("external_schema"):
            continue
        for key in schema["common"]["link_keys"]:
            for target in as_list(d.meta.get(key)):
                if str(target) not in known and str(target) != str(d.meta.get("id")):
                    out.append(Finding("K07", d.path, f"{key} -> {target} does not resolve"))
    out += _check_wip(governed)
    rev = reverse_links(governed)
    status_of = {str(d.meta.get("id")): d.meta.get("status") for d in governed if d.meta.get("id")}
    for d in governed:
        spec = schema["types"].get(d.dtype, {})
        if spec.get("external_schema"):
            continue
        did = str(d.meta.get("id") or "")
        if not did:
            continue
        live_successors = [s for s in rev.get(did, {}).get("superseded_by", ())
                           if status_of.get(s) in ("accepted", "active", "done", "implemented")]
        terminal = schema["superseded_status"].get(d.dtype)
        if live_successors and terminal and d.meta.get("status") != terminal:
            out.append(Finding("K11", d.path,
                               f"superseded by {sorted(live_successors)}; status must be '{terminal}'"))

    # Cross-document & repo-level rules K14, K15, K18
    out += _check_k14(root, schema, docs)
    out += _check_k15(root, schema)
    out += _check_k18(governed, schema)

    # Transitional warning mode: severity set based on schema["lint"]["warn"]
    warn_codes = set(schema.get("lint", {}).get("warn", []))
    for f in out:
        if f.code in warn_codes:
            f.severity = "warning"
        else:
            f.severity = "error"

    if only is not None:
        out = [f for f in out if f.path in only]
    return sorted(out, key=lambda f: (f.path, f.code, f.line))


def wip_by_branch(docs: list[Doc]) -> dict[str, list[str]]:
    """Group in-progress story ids by the branch they declare (ADR-0022).

    Args:
        docs: Documents with frontmatter.

    Returns:
        Mapping branch -> story ids with status in_progress.
    """
    out: dict[str, list[str]] = {}
    for d in docs:
        if d.dtype == "story" and d.meta.get("status") == "in_progress" and d.meta.get("branch"):
            out.setdefault(str(d.meta["branch"]), []).append(str(d.meta.get("id")))
    return out


def _check_wip(docs: list[Doc]) -> list[Finding]:
    """Report K13 when one branch carries more than one in-progress story."""
    out = []
    path_of = {str(d.meta.get("id")): d.path for d in docs}
    for branch, ids in wip_by_branch(docs).items():
        if len(ids) > 1:
            for sid in sorted(ids):
                out.append(Finding("K13", path_of[sid],
                                   f"WIP=1 per worktree: branch {branch} has {sorted(ids)} in_progress"))
    return out


def _legacy_ids(legacy: set[str]) -> set[str]:
    """Derive ids of unmigrated files and declared ids so links to them still resolve."""
    out = _declared_ids(legacy)
    for p in legacy:
        name = p.split("/")[-1]
        m = re.match(r"^(\d{4})-", name)
        if p.startswith("docs/decisions/") and m:
            out.add(f"ADR-{m.group(1)}")
        m = re.match(r"^(US-[0-9A-Z]+)-", name)
        if p.startswith("docs/stories/") and m:
            out.add(m.group(1))
    return out


def staged_paths(root: Path = REPO_ROOT) -> set[str]:
    """List staged added or modified files.

    Args:
        root: Repository root.

    Returns:
        Repo-relative POSIX paths.
    """
    res = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


def _ids_in_git_refs(root: Path, folder: str) -> set[str]:
    """Collect file names under a folder across every local and remote branch."""
    refs = subprocess.run(["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"],
                          cwd=root, capture_output=True, text=True, check=False).stdout.split()
    names: set[str] = set()
    for ref in refs:
        res = subprocess.run(["git", "ls-tree", "--name-only", f"{ref}:{folder}"],
                             cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
        names.update(res.stdout.split())
    return names


def next_number(root: Path, dtype: str, db_path: str | None = None) -> int:
    """Allocate the next free number for a numbered type.

    The scan covers the working tree, every git branch and, for stories, the harness.db rows,
    so two sessions on different branches do not pick the same number.

    Args:
        root: Repository root.
        dtype: One of adr, story, rule.
        db_path: Optional harness.db path for story ids recorded before their files exist.

    Returns:
        Next unused number.
    """
    folder = {"adr": "docs/decisions", "story": "docs/stories", "rule": ".agents/rules"}[dtype]
    pattern = {"adr": r"^(\d{4})-", "story": r"^US-(\d{3})-", "rule": r"^(\d{2})-"}[dtype]
    names = {p.name for p in (root / folder).glob("*.md")} | _ids_in_git_refs(root, folder)
    nums = [int(m.group(1)) for n in names if (m := re.match(pattern, n))]
    if dtype == "story" and db_path and Path(db_path).exists():
        with sqlite3.connect(db_path) as conn:
            for (sid,) in conn.execute("SELECT id FROM story"):
                m = re.match(r"^US-(\d{3})$", sid)
                if m:
                    nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def slugify(text: str) -> str:
    """Make a lowercase ASCII slug from a title.

    Args:
        text: Free-form title.

    Returns:
        Slug of at most eight words joined by hyphens.
    """
    words = re.findall(r"[a-z0-9]+", text.lower().encode("ascii", "ignore").decode())
    return "-".join(words[:8]) or "untitled"


def new_doc(root: Path, dtype: str, title: str, *, lane: str = "normal", author: str = "agent",
            slug: str | None = None, wave: str | None = None, db_path: str | None = None,
            today: date | None = None, adopt_id: str | None = None) -> dict[str, str]:
    """Create a governed document from its template with an allocated id.

    Args:
        root: Repository root.
        dtype: Document type from the schema.
        title: Human-readable title in English.
        lane: Risk lane.
        author: Agent or human name recorded in `authors`.
        slug: Optional slug; derived from the title when omitted.
        wave: Wave code, required for type run.
        db_path: harness.db path used by story allocation.
        today: Date override for tests.
        adopt_id: Existing adr or story id that was registered before its file existed;
            skips allocation after checking that no file already carries it.

    Returns:
        Mapping with the new id and repo-relative path.

    Raises:
        ValueError: When the type is unknown or a required argument is missing.
        FileExistsError: When the target file already exists.
    """
    schema = load_schema(root)
    if dtype not in schema["types"]:
        raise ValueError(f"unknown type '{dtype}', expected one of {list(schema['types'])}")
    today = today or date.today()
    slug = slug or slugify(title)
    spec = schema["types"][dtype]
    globs = spec.get("path_globs") or as_list(spec.get("path_glob"))
    first_glob = globs[0] if globs else f"docs/{dtype}/*.md"
    folder = first_glob.split("*")[0].rstrip("/")
    if adopt_id:
        if not re.match(schema["types"][dtype]["id_pattern"], adopt_id) or dtype not in ("adr", "story"):
            raise ValueError(f"--id {adopt_id} is not a valid {dtype} id; only adr and story ids can be adopted")
        taken = {str(d.meta.get("id")) for d in discover(root, schema) if d.has_frontmatter}
        taken |= _legacy_ids(legacy_files(load_legacy(root)))
        if adopt_id in taken:
            raise ValueError(f"{adopt_id} already has a file")
    if dtype == "adr":
        n = int(adopt_id[4:]) if adopt_id else next_number(root, "adr")
        did, rel = f"ADR-{n:04d}", f"{folder}/{n:04d}-{slug}.md"
    elif dtype == "story":
        n = int(adopt_id[3:]) if adopt_id else next_number(root, "story", db_path)
        did, rel = f"US-{n:03d}", f"{folder}/US-{n:03d}-{slug}.md"
    elif dtype == "rule":
        n = next_number(root, "rule")
        did, rel = f"RULE-{n:02d}", f"{folder}/{n:02d}-{slug}.md"
    elif dtype == "proposal":
        did, rel = f"PRP-{today:%Y%m%d}-{slug}", f"{folder}/{today:%Y%m%d}-{slug}.md"
    elif dtype == "plan":
        stamp = datetime.now().strftime("%H%M")
        did, rel = f"PLN-{today:%Y%m%d}-{stamp}-{slug}", f"plans/{today:%Y%m%d}-{stamp}-{slug}/plan.md"
    elif dtype == "run":
        if not wave:
            raise ValueError("type run requires --wave")
        did, rel = f"RUN-{wave}", f"{folder}/{wave}.md"
    elif dtype == "reference":
        did, rel = f"REF-{slug}", f"docs/{slug}.md"
    elif dtype == "ledger":
        did, rel = f"LDG-{slug}", f"docs/ledgers/{slug}.md"
    elif dtype == "okf":
        did, rel = f"OKF-{slug}", f"okf/{slug}.md"
    elif dtype == "skill":
        did, rel = slug, f".agents/skills/{slug}/SKILL.md"
    else:
        did, rel = f"{dtype.upper() if dtype == 'fact' else 'RB'}-{slug}", f"{folder}/{slug}.md"
    template = (root / TEMPLATE_DIR / f"{dtype}.md").read_text(encoding="utf-8")
    text = (template.replace("{{id}}", did).replace("{{title}}", title)
            .replace("{{date}}", today.isoformat()).replace("{{lane}}", lane)
            .replace("{{author}}", author).replace("{{wave}}", wave or ""))
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return {"id": did, "path": rel}


def effective_status(doc: Doc, rev: dict[str, dict[str, set[str]]]) -> str:
    """Render status with inbound supersession and amendment for the index."""
    did = str(doc.meta.get("id"))
    status = str(doc.meta.get("status"))
    links = rev.get(did, {})
    extra = []
    if links.get("superseded_by"):
        extra.append("by " + ", ".join(sorted(links["superseded_by"])))
    if links.get("amended_by"):
        extra.append("amended by " + ", ".join(sorted(links["amended_by"])))
    return status + (f" ({'; '.join(extra)})" if extra else "")


def build_index(root: Path = REPO_ROOT) -> str:
    """Render docs/INDEX.md from frontmatter.

    Args:
        root: Repository root.

    Returns:
        Markdown text of the index.
    """
    schema = load_schema(root)
    docs = [d for d in discover(root, schema) if d.has_frontmatter]
    legacy = sorted(legacy_files(load_legacy(root)))
    rev = reverse_links(docs)
    lines = [
        "# Knowledge Index",
        "",
        "Generated by `python scripts/harness_cli.py doc index`. Do not edit by hand.",
        "Contract: [docs/knowledge/README.md](knowledge/README.md). Read this index before opening",
        "any governed document; open a body only when its summary is relevant.",
        "",
    ]
    for dtype in schema["types"]:
        group = [d for d in docs if d.dtype == dtype]
        if not group:
            continue
        lines += [f"## {dtype}", "", "| ID | Status | Title | Summary |", "|---|---|---|---|"]
        for d in sorted(group, key=lambda x: str(x.meta.get("id"))):
            rel = os.path.relpath(root / d.path, root / "docs").replace("\\", "/")
            title = str(d.meta.get("title", "")).replace("|", "/")
            summary = str(d.meta.get("summary", "")).replace("|", "/")
            lines.append(f"| [{d.meta.get('id')}]({rel}) | {effective_status(d, rev)} | {title} | {summary} |")
        lines.append("")
    if legacy:
        lines += ["## unmigrated", "",
                  f"{len(legacy)} files still lack frontmatter; see `{LEGACY_PATH}`.", ""]
    return "\n".join(lines)


def write_index(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Write docs/INDEX.md.

    Args:
        root: Repository root.

    Returns:
        Status mapping with the path written.
    """
    (root / INDEX_PATH).write_text(build_index(root) + "\n", encoding="utf-8", newline="\n")
    return {"status": "success", "path": INDEX_PATH}


class IndexCheckResult(NamedTuple):
    """Represent the result of comparing docs/INDEX.md with the generated index.

    Attributes:
        is_synced: True when the file on disk matches the in-memory index.
        diff: Unified diff string when divergent, or empty string when matching.
    """

    is_synced: bool
    diff: str

    @property
    def status(self) -> str:
        """Return status string for JSON serialization."""
        return "success" if self.is_synced else "error"

    @property
    def drift(self) -> bool:
        """Return True if index drift was detected."""
        return not self.is_synced

    @property
    def message(self) -> str:
        """Return diff content or confirmation message."""
        return self.diff if not self.is_synced else "docs/INDEX.md is in sync"


def check_index(root: Path = REPO_ROOT) -> IndexCheckResult:
    """Compare docs/INDEX.md on disk with the in-memory generated index.

    Args:
        root: Repository root.

    Returns:
        IndexCheckResult with sync status and diff output.
    """
    index_file = root / INDEX_PATH
    on_disk = index_file.read_text(encoding="utf-8").strip() if index_file.exists() else ""
    in_mem = build_index(root).strip()
    if on_disk == in_mem:
        return IndexCheckResult(True, "")
    diff_lines = list(difflib.unified_diff(
        on_disk.splitlines(keepends=True),
        in_mem.splitlines(keepends=True),
        fromfile="docs/INDEX.md (disk)",
        tofile="build_index(root) (in-memory)",
    ))
    return IndexCheckResult(False, "".join(diff_lines))


def sync_db(root: Path, db_path: str) -> dict[str, Any]:
    """Upsert story and decision rows in harness.db from frontmatter and report drift.

    Proof columns and trace rows are runtime data and are left untouched.

    Args:
        root: Repository root.
        db_path: harness.db path.

    Returns:
        Counts of upserted rows and ids that exist only in the database.
    """
    docs = [d for d in discover(root) if d.has_frontmatter]
    ts = datetime.now(timezone.utc).isoformat()
    stories = [d for d in docs if d.dtype == "story"]
    adrs = [d for d in docs if d.dtype == "adr"]
    with sqlite3.connect(db_path) as conn:
        for d in stories:
            m = d.meta
            conn.execute(
                """INSERT INTO story (id, title, status, lane, verify_command, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, status=excluded.status,
                   lane=excluded.lane, verify_command=excluded.verify_command,
                   updated_at=excluded.updated_at""",
                (m["id"], m.get("title", ""), m.get("status", "planned"), m.get("lane", "normal"),
                 str(m.get("verify", "")), ts, ts))
        for d in adrs:
            m = d.meta
            conn.execute(
                """INSERT INTO decision (id, title, status, doc_path, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, status=excluded.status,
                   doc_path=excluded.doc_path, updated_at=excluded.updated_at""",
                (m["id"], m.get("title", ""), m.get("status", "proposed"), d.path, ts, ts))
        conn.commit()
        file_ids = {str(d.meta["id"]) for d in stories} | _legacy_ids(legacy_files(load_legacy(root)))
        db_only = sorted(sid for (sid,) in conn.execute("SELECT id FROM story") if sid not in file_ids)
    return {"status": "success", "stories": len(stories), "decisions": len(adrs),
            "db_only_stories": db_only}


def _format_evidence_block(evidence: Any) -> str:
    """Format evidence into YAML frontmatter string preserving valid prefixes.

    Args:
        evidence: Evidence string or list/tuple of evidence strings.

    Returns:
        Formatted YAML string for frontmatter evidence.
    """
    if isinstance(evidence, str):
        if evidence.strip().startswith("[") and evidence.strip().endswith("]"):
            try:
                import json
                items = json.loads(evidence)
            except Exception:
                items = [evidence.strip("[]").strip()]
        else:
            items = [evidence]
    elif isinstance(evidence, (list, tuple)):
        items = list(evidence)
    else:
        items = [str(evidence)]

    valid_prefixes = ("commit:", "path:", "metric:", "test:", "wave:", "url:", "operator:", "trace:")
    formatted = []
    for it in items:
        s = str(it).strip()
        if not s:
            continue
        if not any(s.startswith(p) for p in valid_prefixes):
            s = f"operator: {s}"
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            formatted.append(f"  - {s}")
        elif any(c in s for c in [": ", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "<", ">", "=", "!", "%", "@", "\\"]) or " " in s:
            escaped = s.replace('"', '\\"')
            formatted.append(f'  - "{escaped}"')
        else:
            formatted.append(f"  - {s}")
    if not formatted:
        return "evidence: []"
    return "evidence:\n" + "\n".join(formatted)


def _replace_evidence_in_frontmatter(fm: str, ev_block: str) -> str:
    """Replace or insert evidence block in frontmatter preserving lines.

    Args:
        fm: Frontmatter string without bounding markers.
        ev_block: Formatted evidence block string.

    Returns:
        Updated frontmatter string.
    """
    lines = fm.splitlines()
    out = []
    in_evidence = False
    evidence_replaced = False
    for line in lines:
        if re.match(r"^evidence:\s*", line):
            in_evidence = True
            evidence_replaced = True
            out.append(ev_block)
            continue
        if in_evidence:
            if re.match(r"^\s+-\s+", line):
                continue
            else:
                in_evidence = False
        out.append(line)
    if not evidence_replaced:
        new_out = []
        inserted = False
        for line in out:
            if re.match(r"^summary:\s*", line) and not inserted:
                new_out.append(ev_block)
                inserted = True
            new_out.append(line)
        if not inserted:
            new_out.append(ev_block)
        out = new_out
    return "\n".join(out)


def set_story_status(
    root: Path,
    story_id: str,
    status: str,
    *,
    branch: str | None = None,
    evidence: str | list[str] | None = None,
    db_path: str | Path | None = None,
) -> Path:
    """Modify story frontmatter atomically, validate schema/WIP, sync DB, and regenerate index.

    Args:
        root: Repository root.
        story_id: Story identifier (e.g. 'US-051').
        status: Target status ('planned', 'in_progress', 'implemented', 'changed', 'retired', etc.).
        branch: Git branch name (required when status is 'in_progress').
        evidence: Optional evidence string or list of evidence items.
        db_path: Optional path to SQLite harness.db.

    Returns:
        Path to the modified story file.

    Raises:
        FileNotFoundError: If the story markdown file cannot be found.
        ValueError: If validation against schema v2 or WIP=1 constraint fails.
    """
    stories_dir = root / "docs" / "stories"
    matches = sorted(stories_dir.glob(f"{story_id}-*.md")) + sorted(stories_dir.glob(f"{story_id}.md"))
    if not matches:
        matches = sorted(p for p in stories_dir.glob(f"{story_id}*.md") if p.name.startswith((f"{story_id}-", f"{story_id}.")))
    if not matches:
        raise FileNotFoundError(f"No story file found matching '{story_id}' in {stories_dir}")

    target_path = matches[0]
    original_text = target_path.read_text(encoding="utf-8")

    m = _FRONTMATTER_RE.match(original_text)
    if not m:
        raise ValueError(f"Story {target_path} lacks valid YAML frontmatter")

    fm = m.group(1)
    body = original_text[m.end():]

    # 1. Update status
    if re.search(r"(?m)^status:\s*.*$", fm):
        fm = re.sub(r"(?m)^status:\s*.*$", f"status: {status}", fm)
    else:
        fm = f"status: {status}\n" + fm

    # 2. Update updated date
    today_str = date.today().isoformat()
    if re.search(r"(?m)^updated:\s*.*$", fm):
        fm = re.sub(r"(?m)^updated:\s*.*$", f"updated: {today_str}", fm)
    else:
        if re.search(r"(?m)^created:\s*.*$", fm):
            fm = re.sub(r"(?m)^(created:\s*.*)$", rf"\1\nupdated: {today_str}", fm)
        else:
            fm = re.sub(r"(?m)^(status:\s*.*)$", rf"\1\nupdated: {today_str}", fm)

    # 3. Update branch if provided
    if branch is not None:
        if re.search(r"(?m)^branch:\s*.*$", fm):
            fm = re.sub(r"(?m)^branch:\s*.*$", f"branch: {branch}", fm)
        else:
            fm = re.sub(r"(?m)^(status:\s*.*)$", rf"\1\nbranch: {branch}", fm)

    # 4. Update evidence if provided
    if evidence is not None:
        ev_block = _format_evidence_block(evidence)
        fm = _replace_evidence_in_frontmatter(fm, ev_block)

    new_content = f"---\n{fm.strip()}\n---\n{body}"

    # Atomic write to temporary file in same directory, then os.replace
    tmp_path = target_path.with_suffix(".tmp")
    tmp_path.write_text(new_content, encoding="utf-8", newline="\n")
    os.replace(tmp_path, target_path)

    # Validation re-check
    schema = load_schema(root)
    doc = parse_doc(target_path, root, "story")
    findings = _check_doc(doc, schema, root)
    if status == "in_progress":
        docs = [d for d in discover(root, schema) if d.has_frontmatter]
        findings += _check_wip(docs)

    errors = [f for f in findings if f.severity == "error"]
    if errors:
        # Rollback on validation failure
        target_path.write_text(original_text, encoding="utf-8", newline="\n")
        raise ValueError(f"Validation failed for {story_id}: {[str(f) for f in errors]}")

    # Synchronize SQLite harness.db table story
    target_db = str(db_path or (root / "harness.db"))
    if os.path.exists(target_db):
        ts = datetime.now(timezone.utc).isoformat()
        ev_db = None
        if evidence is not None:
            if isinstance(evidence, (list, tuple)):
                ev_db = "; ".join(str(e) for e in evidence)
            else:
                ev_db = str(evidence)
        with sqlite3.connect(target_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM story WHERE id = ?", (story_id,)).fetchone()
            if row:
                u_proof = row["unit_proof"]
                if status == "implemented" and not (row["unit_proof"] or row["integration_proof"] or row["e2e_proof"] or row["platform_proof"]):
                    u_proof = 1
                conn.execute(
                    """
                    UPDATE story SET status = ?, updated_at = ?,
                                     git_branch = COALESCE(?, git_branch),
                                     evidence = COALESCE(?, evidence),
                                     unit_proof = ?
                    WHERE id = ?
                    """,
                    (status, ts, branch, ev_db, u_proof, story_id),
                )
            else:
                u_proof = 1 if status == "implemented" else 0
                conn.execute(
                    """
                    INSERT INTO story (id, title, status, lane, git_branch, evidence, unit_proof, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (story_id, doc.meta.get("title", story_id), status, doc.meta.get("lane", "normal"),
                     branch, ev_db, u_proof, ts, ts),
                )
            conn.commit()

    # Regenerate docs/INDEX.md
    write_index(root)
    return target_path


# ---------------------------------------------------------------------------
# Presentation Checkers (ported from project/scripts/doc_lint.py)
# ---------------------------------------------------------------------------

def _docstring_lines(tree: ast.AST) -> set[int]:
    """Collect the line numbers occupied by module, class and function docstrings."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                c = body[0].value
                lines.update(range(c.lineno, (c.end_lineno or c.lineno) + 1))
    return lines


def lint_python(path: str, text: str) -> list[Finding]:
    """Lint one Python file: banned phrases in docstrings/comments; emoji and codes in strings."""
    out: list[Finding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Finding("L00", path, f"không đọc được cú pháp: {exc.msg}", line=exc.lineno or 0)]
    doc_lines = _docstring_lines(tree)
    src_lines = text.splitlines()
    for no in sorted(doc_lines):
        m = _BLACKLIST_DEFAULT_VI_RE.search(src_lines[no - 1])
        if m:
            out.append(Finding("L01", path, f"từ cấm \"{m.group(1)}\" trong docstring", line=no))
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            m = _BLACKLIST_DEFAULT_VI_RE.search(tok.string)
            if m:
                out.append(Finding("L01", path, f"từ cấm \"{m.group(1)}\" trong comment", line=tok.start[0]))
            if _EMOJI_RE.search(tok.string):
                out.append(Finding("L02", path, "emoji trong comment", line=tok.start[0]))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node.lineno in doc_lines:
            continue
        s = node.value
        line_src = src_lines[node.lineno - 1]
        if _EMOJI_RE.search(s) and not any(a in line_src for a in _EMOJI_ALLOW):
            out.append(Finding("L02", path, "emoji trong chuỗi hiển thị", line=node.lineno))
        low = s.lower()
        for old, new in _LEGACY_TERMS_DOCLINT:
            if old in low and not any(a in s for a in _LEGACY_ALLOW):
                out.append(Finding("L03", path, f"tên cũ \"{old}\", dùng \"{new}\"", line=node.lineno))
        m = _INTERNAL_CODE_RE.search(s)
        if m:
            out.append(Finding("L04", path, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc", line=node.lineno))
    return out


def lint_html(path: str, text: str) -> list[Finding]:
    """Lint one HTML page: emoji, banned phrases, legacy names and internal codes in visible text."""
    out: list[Finding] = []
    for no, line in enumerate(text.splitlines(), 1):
        visible = re.sub(r"<[^>]+>", " ", line)
        if _EMOJI_RE.search(line):
            out.append(Finding("L02", path, "emoji trong giao diện", line=no))
        m = _BLACKLIST_DEFAULT_VI_RE.search(visible)
        if m and "//" not in line.split(m.group(0))[0]:
            out.append(Finding("L01", path, f"từ cấm \"{m.group(1)}\"", line=no))
        for old, new in _LEGACY_TERMS_DOCLINT:
            if old in line.lower():
                out.append(Finding("L03", path, f"tên cũ \"{old}\", dùng \"{new}\"", line=no))
        m = _INTERNAL_CODE_RE.search(line)
        if m:
            out.append(Finding("L04", path, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc", line=no))
    return out


def lint_markdown(path: str, text: str, *, root: Path = REPO_ROOT, reader_facing: bool = True,
                  check_terms: bool = True, adr_number: int | None = None,
                  check_length: bool = True) -> list[Finding]:
    """Forwarding helper for legacy markdown linting tests."""
    out: list[Finding] = []
    in_fence = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = re.sub(r"`[^`]*`", " ", line)
        prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", prose)
        prose = re.sub(r"[*_>#]", "", prose)
        m = _BLACKLIST_DEFAULT_VI_RE.search(prose)
        if m:
            out.append(Finding("L01", path, f"từ cấm \"{m.group(1)}\" (rule 06 mục 2)", line=no))
        if _EMOJI_RE.search(line):
            out.append(Finding("L02", path, "có emoji hoặc biểu tượng trang trí", line=no))
        if check_terms:
            low = line.lower()
            for old, new in _LEGACY_TERMS_DOCLINT:
                if old in low and not any(a in line for a in _LEGACY_ALLOW):
                    out.append(Finding("L03", path, f"tên cũ \"{old}\", dùng \"{new}\"", line=no))
        if reader_facing:
            m = _INTERNAL_CODE_RE.search(re.sub(r"`[^`]*`", " ", line))
            if m:
                out.append(Finding("L04", path, f"mã nội bộ \"{m.group(0)}\" lộ ra người đọc", line=no))
        stripped = line.strip()
        if check_length and stripped and not stripped.startswith(("|", "#", "---", "<!--")):
            for sentence in re.split(r"(?<=[.!?])\s+", prose):
                words = len(sentence.split())
                if words > 25:
                    out.append(Finding("L08", path, f"câu {words} từ, tối đa 25", line=no))
                    break
    return out


def lint_presentation_repo(root: Path = REPO_ROOT) -> list[Finding]:
    """Lint the whole declared presentation scope of the repository."""
    schema = load_schema(root)
    out: list[Finding] = []
    py_globs = schema.get("presentation", {}).get("python_globs", [
        "project/src/ops/*.py", "project/scripts/ops_daemon.py", "project/scripts/ops_console.py"
    ])
    html_globs = schema.get("presentation", {}).get("html_globs", [
        "project/src/ops/web/*.html"
    ])
    for pattern in py_globs:
        for f in sorted(root.glob(pattern)):
            out += lint_python(f.relative_to(root).as_posix(), f.read_text(encoding="utf-8"))
    for pattern in html_globs:
        for f in sorted(root.glob(pattern)):
            out += lint_html(f.relative_to(root).as_posix(), f.read_text(encoding="utf-8"))
    return sorted(out, key=lambda x: (x.path, x.line, x.code))
