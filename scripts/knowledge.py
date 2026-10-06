"""Validate, allocate, index and sync governed knowledge documents under the ADR-0021 contract."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = "docs/knowledge/schema.yaml"
LEGACY_PATH = "docs/knowledge/legacy.txt"
INDEX_PATH = "docs/INDEX.md"
TEMPLATE_DIR = "docs/templates"

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
_H2_RE = re.compile(r"^##\s+(?:\d+(?:\.\d+)*\.?\s+)?(.+?)\s*$")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕✅❌]|️")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}")
_LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")
_NUM_IN_ID_RE = re.compile(r"(\d+)$")


@dataclass
class Finding:
    """One contract violation.

    Attributes:
        code: Rule code, K00 to K12.
        path: Repo-relative POSIX path.
        message: What is wrong and what is expected.
    """

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path} {self.code} {self.message}"


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
    has_fm = bool(m) and "type" in meta
    offset = text[:m.end()].count("\n") if m else 0
    doc = Doc(rel, dtype, meta, body, has_fm, error, offset)
    # Template guidance lives in HTML comments and must not count toward content floors.
    doc.sections, doc.section_order = split_sections(re.sub(r"<!--.*?-->", "", body, flags=re.S))
    return doc


def _type_for_path(rel: str, schema: dict[str, Any]) -> str | None:
    """Return the document type whose glob matches a repo-relative path."""
    for name, spec in schema["types"].items():
        if fnmatch(rel, spec["path_glob"]) and rel.count("/") == spec["path_glob"].count("/"):
            return name
    return None


def discover(root: Path = REPO_ROOT, schema: dict[str, Any] | None = None) -> list[Doc]:
    """Collect every file that falls under a governed path glob.

    Args:
        root: Repository root.
        schema: Loaded schema; loaded from disk when omitted.

    Returns:
        Parsed documents sorted by path.
    """
    schema = schema or load_schema(root)
    docs = []
    for name, spec in schema["types"].items():
        for p in sorted(root.glob(spec["path_glob"])):
            if p.is_file() and p.suffix == ".md":
                docs.append(parse_doc(p, root, name))
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
    """Flag Vietnamese prose in an English body and style violations."""
    out: list[Finding] = []
    lang_spec = schema["language"]
    vi = set(lang_spec["vi_chars"])
    banned = [b.lower() for b in lang_spec["banned_phrases"]]
    max_words = lang_spec["max_sentence_words"]
    english = doc.meta.get("lang") == "en"
    offset = doc.body_offset
    in_fence = False
    for no, raw in enumerate(doc.body.splitlines(), 1 + offset):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _EMOJI_RE.search(raw):
            out.append(Finding("K10", doc.path, f"line {no}: emoji or decorative symbol"))
        if not english:
            continue
        line = re.sub(r"`[^`]*`", " ", raw)
        if line.lstrip().startswith(">"):
            continue
        unquoted = re.sub(r"\"[^\"]*\"|“[^”]*”|'[^']*'", " ", line)
        if any(ch in vi for ch in unquoted):
            out.append(Finding("K09", doc.path,
                               f"line {no}: Vietnamese text in a lang: en body; quote it or translate"))
        low = line.lower()
        for phrase in banned:
            if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", low):
                out.append(Finding("K10", doc.path, f"line {no}: banned phrase \"{phrase}\""))
        stripped = line.strip()
        if stripped and not stripped.startswith(("|", "#", "<!--")):
            prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
            for sentence in re.split(r"(?<=[.!?])\s+", prose):
                if len(sentence.split()) > max_words:
                    out.append(Finding("K10", doc.path,
                                       f"line {no}: sentence of {len(sentence.split())} words, max {max_words}"))
                    break
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
    if doc.dtype in ("fact", "runbook"):
        return did.split("-", 1)[1] + ".md" if "-" in did else None
    if doc.dtype == "proposal":
        return did.replace("PRP-", "", 1) + ".md"
    if doc.dtype == "run":
        return did.replace("RUN-", "", 1) + ".md"
    if doc.dtype == "plan":
        return did.replace("PLN-", "", 1)
    return None


def _check_doc(doc: Doc, schema: dict[str, Any]) -> list[Finding]:
    """Validate one document that has frontmatter against its type spec."""
    out: list[Finding] = []
    spec = schema["types"][doc.dtype]
    common = schema["common"]
    meta = doc.meta
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
        if key in meta and meta[key] not in allowed:
            out.append(Finding("K02", doc.path, f"{key} '{meta[key]}' not in {allowed}"))
    if meta.get("lang") not in spec["lang"]:
        out.append(Finding("K02", doc.path, f"lang '{meta.get('lang')}' not in {spec['lang']}"))
    did = str(meta.get("id", ""))
    if not re.match(spec["id_pattern"], did):
        out.append(Finding("K03", doc.path, f"id '{did}' does not match {spec['id_pattern']}"))
    else:
        stem = _expected_stem(doc, spec)
        rel_name = doc.path.split("/")[-2] if doc.dtype == "plan" else doc.path.split("/")[-1]
        if stem and not (rel_name == stem or rel_name.startswith(stem)):
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
    for sec in spec["sections"]:
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

    Cross-document checks (duplicate ids, link targets, supersession) always load the full
    corpus so that a staged subset is judged against the whole repository.

    Args:
        root: Repository root.
        only: Repo-relative paths to report on; None reports on everything.

    Returns:
        Findings sorted by path.
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
            if d.path not in legacy and not schema["types"][d.dtype].get("opt_in"):
                out.append(Finding("K00", d.path, "no frontmatter; create with `harness_cli.py doc new`"))
            continue
        governed.append(d)
        out += _check_doc(d, schema)
    ids: dict[str, str] = {}
    for d in governed:
        did = str(d.meta.get("id"))
        if did in ids:
            out.append(Finding("K04", d.path, f"duplicate id {did}, also in {ids[did]}"))
        ids.setdefault(did, d.path)
    known = set(ids) | _legacy_ids(legacy)
    for d in governed:
        for key in schema["common"]["link_keys"]:
            for target in as_list(d.meta.get(key)):
                if str(target) not in known and str(target) != str(d.meta.get("id")):
                    out.append(Finding("K07", d.path, f"{key} -> {target} does not resolve"))
    out += _check_wip(governed)
    rev = reverse_links(governed)
    status_of = {str(d.meta.get("id")): d.meta.get("status") for d in governed}
    for d in governed:
        did = str(d.meta.get("id"))
        live_successors = [s for s in rev.get(did, {}).get("superseded_by", ())
                           if status_of.get(s) in ("accepted", "active", "done", "implemented")]
        terminal = schema["superseded_status"].get(d.dtype)
        if live_successors and terminal and d.meta.get("status") != terminal:
            out.append(Finding("K11", d.path,
                               f"superseded by {sorted(live_successors)}; status must be '{terminal}'"))
    if only is not None:
        out = [f for f in out if f.path in only]
    return sorted(out, key=lambda f: (f.path, f.code))


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
    folder = Path(schema["types"][dtype]["path_glob"]).parent.as_posix()
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
