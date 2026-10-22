"""Module boundary checks from ADR-0027, with allowlists that may only shrink."""
from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"

PLUMBING_HOMES = {"src/core/paths.py"}
DB_HOMES_PREFIX = "src/db/"

# Remaining violations at the time each rule was introduced. Remove entries as code moves.
ALLOW_SCRIPTS_IMPORT: set[str] = {
    'scripts/article_run.py',
    'scripts/handoff.py',
    'scripts/maintenance/refresh_aliases.py',
    'scripts/pipeline_radar.py',
    'src/ops/daemon.py',
    'src/ops/sensor.py',
    'src/ops/wave_flow.py',
}
ALLOW_SRC_SYS_PATH: set[str] = {
    'src/morninger.py',
}
ALLOW_SQLITE_CONNECT: set[str] = set()
ALLOW_PROJECT_ROOT: set[str] = set()
ALLOW_PACKAGE_EDGES: set[tuple[str, str]] = {
    ('agent', 'handoff'),
    ('core', 'crawler'),
    ('core', 'db'),
    ('crawler', 'core'),
    ('db', 'core'),
    ('export', 'lakehouse'),
    ('handoff', 'agent'),
    ('lakehouse', 'export'),
}


# Every CLI under project/scripts with its caller. A new script needs an entry here (ADR-0027.D6).
SCRIPT_INVENTORY: dict[str, str] = {
    "scripts/agent_ingest.py": "article_run --finish ingest step",
    "scripts/article_expand.py": "article_run --finish expand step",
    "scripts/article_pack.py": "article_run wave preparation",
    "scripts/article_run.py": "pipeline.yaml wave lifecycle, ops wave_flow",
    "scripts/article_tick.py": "ops daemon tick and pipeline lock",
    "scripts/build_article_prefix.py": "article_run prefix check, operator rebuild",
    "scripts/build_entities.py": "operator catalog rebuild",
    "scripts/capture_reconcile.py": "pipeline.yaml sitemap reconcile",
    "scripts/compile_users.py": "operator subscription compile",
    "scripts/ctx_probe.py": "article_run context probe",
    "scripts/doc_lint.py": "test_doc_lint presentation lint",
    "scripts/estimate_wave.py": "token_ledger wave estimate",
    "scripts/handoff.py": "article_run --finish handoff step",
    "scripts/inspect_catalog.py": "operator catalog lookup",
    "scripts/l1_ingest.py": "article_run --finish ingest step",
    "scripts/lakehouse_cli.py": "ADR-0026 dropzone verify",
    "scripts/maintenance/audit_codebase.py": "harness_cli audit --codebase",
    "scripts/maintenance/backfill_deferred.py": "morninger backfill job",
    "scripts/maintenance/migrate_users_output.py": "US-045 pending operator migration",
    "scripts/maintenance/refresh_aliases.py": "operator alias refresh",
    "scripts/ops_console.py": "ops_install.ps1 console shortcut",
    "scripts/ops_daemon.py": "Task Scheduler news-scape-ops",
    "scripts/ops_install.ps1": "operator Task Scheduler install",
    "scripts/pipeline_radar.py": "AGENTS.md radar entry point",
    "scripts/provider_conformance.py": "ADR-0017 golden set gate",
    "scripts/publish.py": "ADR-0026 publish path",
    "scripts/rederive_from_bronze.py": "operator Silver re-derive",
    "scripts/refresh_watchlist.py": "pipeline_radar watchlist refresh",
    "scripts/run_backlog_opencode.ps1": "operator opencode backlog driver",
    "scripts/run_backlog_opencode.py": "operator opencode backlog driver",
    "scripts/run_once.py": "pipeline.yaml capture cycle",
    "scripts/signal_build.py": "pipeline.yaml insight signals",
    "scripts/story_cluster.py": "pipeline.yaml story clustering",
    "scripts/token_ledger.py": "article_run --finish ledger step",
    "scripts/validate_capture.py": "pipeline_radar capture validation",
    "scripts/write_user_output.py": "pipeline.yaml delivery, ops wave_flow",
}


def _rel(path: Path) -> str:
    """Return a project-relative POSIX path.

    Args:
        path: File under the project root.

    Returns:
        Path relative to the project root.
    """
    return path.relative_to(PROJECT_ROOT).as_posix()


def _code_files() -> list[Path]:
    """List every Python file under src and scripts.

    Returns:
        Sorted file paths.
    """
    return sorted(p for base in (SRC, SCRIPTS) for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _tree(path: Path) -> ast.Module:
    """Parse one file.

    Args:
        path: Python source file.

    Returns:
        Parsed module.
    """
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.Module) -> set[str]:
    """Collect absolute module names imported anywhere in a module.

    Args:
        tree: Parsed module.

    Returns:
        Imported module names.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _calls(tree: ast.Module, dotted: str) -> bool:
    """Tell whether a module calls a dotted function such as `sys.path.insert`.

    Args:
        tree: Parsed module.
        dotted: Dotted call target.

    Returns:
        True when the call appears.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == dotted:
            return True
    return False


def _assigns(tree: ast.Module, name: str) -> bool:
    """Tell whether a module assigns a module-level name.

    Args:
        tree: Parsed module.
        name: Variable name.

    Returns:
        True when a top-level assignment binds the name.
    """
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return True
    return False


def scripts_import_violations() -> set[str]:
    """Find files under src or scripts that import the `scripts` package.

    Returns:
        Project-relative paths.
    """
    return {_rel(p) for p in _code_files()
            if any(m == "scripts" or m.startswith("scripts.") for m in _imported_modules(_tree(p)))}


def src_sys_path_violations() -> set[str]:
    """Find src modules that change `sys.path`.

    Returns:
        Project-relative paths.
    """
    return {_rel(p) for p in _code_files() if _rel(p).startswith("src/")
            and (_calls(_tree(p), "sys.path.insert") or _calls(_tree(p), "sys.path.append"))}


def sqlite_connect_violations() -> set[str]:
    """Find files outside src/db and src/core/paths.py that call `sqlite3.connect`.

    Returns:
        Project-relative paths.
    """
    return {_rel(p) for p in _code_files()
            if not _rel(p).startswith(DB_HOMES_PREFIX) and _rel(p) not in PLUMBING_HOMES
            and _calls(_tree(p), "sqlite3.connect")}


def project_root_violations() -> set[str]:
    """Find files outside src/core/paths.py that define `PROJECT_ROOT`.

    Returns:
        Project-relative paths.
    """
    return {_rel(p) for p in _code_files() if _rel(p) not in PLUMBING_HOMES and _assigns(_tree(p), "PROJECT_ROOT")}


def _package_of(rel: str) -> str:
    """Map a src file to its top-level package name.

    Args:
        rel: Project-relative path under src.

    Returns:
        Package name, or the module stem for top-level modules.
    """
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 else parts[1][:-3]


def package_edges() -> set[tuple[str, str]]:
    """Collect import edges between top-level src packages.

    Returns:
        Pairs (importer, imported) with distinct packages.
    """
    edges: set[tuple[str, str]] = set()
    for p in _code_files():
        rel = _rel(p)
        if not rel.startswith("src/"):
            continue
        a = _package_of(rel)
        for m in _imported_modules(_tree(p)):
            parts = m.split(".")
            if parts[0] == "src" and len(parts) > 1 and parts[1] != a:
                edges.add((a, parts[1]))
    return edges


def cyclic_edges(edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Keep the edges that lie on a cycle of the package graph.

    Args:
        edges: Directed package edges.

    Returns:
        Edges (a, b) where b reaches a.
    """
    graph: dict[str, set[str]] = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)

    def reaches(start: str, goal: str) -> bool:
        seen, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node == goal:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(graph.get(node, ()))
        return False

    return {(a, b) for a, b in edges if reaches(b, a)}


def _check(found: set, allowed: set, rule: str) -> None:
    """Fail on new violations and on stale allowlist entries.

    Args:
        found: Violations found now.
        allowed: Allowlisted violations.
        rule: Rule label for the message.
    """
    new = sorted(found - allowed)
    stale = sorted(allowed - found)
    assert not new, f"{rule}: new violations {new}"
    assert not stale, f"{rule}: fixed, remove from the allowlist {stale}"


def test_no_import_of_scripts_package():
    _check(scripts_import_violations(), ALLOW_SCRIPTS_IMPORT, "ADR-0027.D3")


def test_src_does_not_touch_sys_path():
    _check(src_sys_path_violations(), ALLOW_SRC_SYS_PATH, "ADR-0027.D4 sys.path")


def test_sqlite_connect_only_in_db_layer():
    _check(sqlite_connect_violations(), ALLOW_SQLITE_CONNECT, "ADR-0027.D4 sqlite3.connect")


def test_project_root_only_in_paths():
    _check(project_root_violations(), ALLOW_PROJECT_ROOT, "ADR-0027.D4 PROJECT_ROOT")


def test_no_package_cycles():
    _check(cyclic_edges(package_edges()), ALLOW_PACKAGE_EDGES, "ADR-0027.D1 cycles")


def test_every_script_has_a_declared_caller():
    found = {_rel(p) for p in SCRIPTS.rglob("*") if p.is_file() and p.suffix in (".py", ".ps1")
             and "__pycache__" not in p.parts}
    _check(found, set(SCRIPT_INVENTORY), "ADR-0027.D6 script inventory")
