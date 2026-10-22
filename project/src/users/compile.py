"""Compile user subscription data from Excel/CSV files into YAML config under project/config/entities/users/, validating through EntityRegistry and reporting unrecognized entities."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import yaml

from src.core import paths
from src.core.user_manifest import load_user_manifest
from src.core.paths import PROJECT_ROOT

DEFAULT_SUBSCRIPTIONS_ROOT = paths.subscriptions_dir()
# The legacy `users/input` layout is copied to `<root>/inputs/users` during the data migration.
LEGACY_INPUT_ROOT = paths.inputs_dir() / "users"
DEFAULT_INPUT_ROOT = DEFAULT_SUBSCRIPTIONS_ROOT if DEFAULT_SUBSCRIPTIONS_ROOT.exists() else LEGACY_INPUT_ROOT
DEFAULT_OUTPUT_ROOT = paths.users_output_dir()
USERS_CONFIG_DIR = PROJECT_ROOT / "config" / "entities" / "users"

# Valid groups in the entities sheet, matching EntityRegistry.select.
GROUP_KEYS = ("tickers", "etfs", "indices", "exchanges", "industries", "nations", "themes", "macro", "assets", "institutions", "entities")
_UPPER_GROUPS = ("tickers", "etfs", "indices", "exchanges", "industries", "nations", "themes", "macro", "assets", "institutions")


def _user_from_filename(filename: str) -> str:
    """Extract the user name from a subscription file name.

    Args:
        filename: Subscription file name, optionally ending in `_news`.

    Returns:
        The user name.
    """
    stem = Path(filename).stem
    if stem.lower().endswith("_news"):
        return stem[:-5]
    return stem


# ---- CSV & Excel I/O ----------------------------------------------------------
def read_user_csv(path: str | Path) -> tuple[dict, dict]:
    """Read a user subscription CSV file.

    Supports both the horizontal matrix layout (columns are entity groups) and the vertical layout (category, code).

    Args:
        path: Path of the subscription CSV file.

    Returns:
        Tuple of the entity catalog dict and the user metadata dict.
    """
    import csv
    path = Path(path)
    doc: dict[str, list[str]] = {}
    meta: dict = {"user": _user_from_filename(path.name)}
    
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        lines = [line for line in f if line.strip() and not line.strip().startswith("#")]
    
    if not lines:
        return _normalize(doc), meta

    # Detect the delimiter automatically (comma, tab or semicolon).
    sample = "\n".join(lines[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = "\t" if "\t" in lines[0] else (";" if ";" in lines[0] else ",")

    reader = csv.reader(lines, delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return _normalize(doc), meta

    headers = [h.strip().lower() for h in rows[0]]
    
    # Vertical layout (category, code).
    if "category" in headers or "group" in headers or "type" in headers:
        cat_idx = headers.index("category") if "category" in headers else (headers.index("group") if "group" in headers else headers.index("type"))
        code_idx = headers.index("code") if "code" in headers else (headers.index("value") if "value" in headers else (1 if len(headers) > 1 else 0))
        for r in rows[1:]:
            if len(r) > max(cat_idx, code_idx):
                c = r[cat_idx].strip().lower()
                v = r[code_idx].strip()
                if c in GROUP_KEYS and v:
                    doc.setdefault(c, []).append(v)
    else:
        # Horizontal layout (each column is one group).
        col_idx = {h: i for i, h in enumerate(headers) if h in GROUP_KEYS}
        for r in rows[1:]:
            for key, idx in col_idx.items():
                if idx < len(r) and r[idx].strip():
                    doc.setdefault(key, []).append(r[idx].strip())

    return _normalize(doc), meta


def write_user_csv(path: str | Path, doc: dict, meta: dict | None = None) -> Path:
    """Write a user catalog to a CSV file in the horizontal matrix layout.

    Args:
        path: Destination CSV path.
        doc: Entity catalog keyed by group.
        meta: Additional user metadata; not written to the CSV.

    Returns:
        Path of the file written.
    """
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    cols = [doc.get(k, []) for k in GROUP_KEYS]
    max_rows = max((len(c) for c in cols), default=0)
    
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(GROUP_KEYS))
        for i in range(max_rows):
            w.writerow([cols[j][i] if i < len(cols[j]) else "" for j in range(len(GROUP_KEYS))])
    return path


def read_user_xlsx(path: str | Path) -> tuple[dict, dict]:
    """Read a user subscription Excel file.

    Args:
        path: Path of the Excel (.xlsx) file.

    Returns:
        Tuple of the entity catalog dict and the user metadata dict.
    """
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    doc: dict[str, list[str]] = {}
    
    target_sheet = None
    if "entities" in wb.sheetnames:
        target_sheet = wb["entities"]
    elif "subscriptions" in wb.sheetnames:
        target_sheet = wb["subscriptions"]
    elif wb.sheetnames:
        target_sheet = wb.worksheets[0]

    if target_sheet is not None:
        rows = list(target_sheet.iter_rows(values_only=True))
        if rows:
            headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
            col_idx = {h: i for i, h in enumerate(headers) if h in GROUP_KEYS}
            for key, idx in col_idx.items():
                vals: list[str] = []
                for r in rows[1:]:
                    if idx < len(r) and r[idx] not in (None, ""):
                        v = str(r[idx]).strip()
                        if v:
                            vals.append(v)
                if vals:
                    doc[key] = vals

    meta: dict = {"user": _user_from_filename(path.name)}
    if "meta" in wb.sheetnames:
        for r in wb["meta"].iter_rows(values_only=True):
            if not r or not r[0]:
                continue
            key = str(r[0]).strip().lower()
            if key == "key":
                continue
            meta[key] = r[1] if len(r) > 1 else None
    wb.close()
    return _normalize(doc), meta


def write_user_xlsx(path: str | Path, doc: dict, meta: dict | None = None) -> Path:
    """Write a subscription catalog to a standard-format Excel file.

    Args:
        path: Destination file path.
        doc: Entity catalog keyed by group.
        meta: Optional additional user metadata.

    Returns:
        Path of the saved Excel file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "entities"
    ws.append(list(GROUP_KEYS))
    cols = [doc.get(k, []) for k in GROUP_KEYS]
    for i in range(max((len(c) for c in cols), default=0)):
        ws.append([c[i] if i < len(c) else None for c in cols])
    if meta:
        ms = wb.create_sheet("meta")
        ms.append(["key", "value"])
        for k, v in meta.items():
            ms.append([k, v])
    wb.save(path)
    return path


def read_user_file(path: str | Path) -> tuple[dict, dict]:
    """Detect the file format (.csv or .xlsx) and read the subscription content.

    Args:
        path: Path of the user subscription file.

    Returns:
        Tuple of the entity catalog dict and the user metadata dict.

    Raises:
        ValueError: If the file format is not supported.
    """
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return read_user_csv(p)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return read_user_xlsx(p)
    raise ValueError(f"Không hỗ trợ định dạng file: {p.suffix}")


def _normalize(doc: dict) -> dict:
    """Normalize catalog data by trimming whitespace and uppercasing codes."""
    out: dict[str, list[str]] = {}
    for key, vals in doc.items():
        if not vals:
            continue
        if key in _UPPER_GROUPS:
            out[key] = [str(v).strip().upper() for v in vals]
        else:
            out[key] = [str(v).strip() for v in vals]
    return out


# ---- compile ------------------------------------------------------------------
_YAML_HEADER = (
    "# AUTO-GENERATED từ users/subscriptions/{name}_news.csv — ĐỪNG sửa tay.\n"
    "# Chạy lại: python scripts/compile_users.py --all\n"
)


def _write_yaml(yaml_path: Path, name: str, doc: dict) -> None:
    """Write subscription data to a YAML file with an auto-generated warning header."""
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {k: doc[k] for k in GROUP_KEYS if doc.get(k)},
        allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    yaml_path.write_text(_YAML_HEADER.format(name=name) + body, encoding="utf-8")


def compile_user(name: str, file_path: str | Path, registry,
                 *, users_config_dir: str | Path = USERS_CONFIG_DIR,
                 input_dir: str | Path | None = None) -> dict:
    """Compile one user's subscription file into a system YAML file.

    Args:
        name: User name.
        file_path: Path of the subscription file (.csv or .xlsx).
        registry: EntityRegistry used to map and validate entities.
        users_config_dir: Destination directory of the YAML config.
        input_dir: Directory of the subscription files, where the unknown-entity warning file is written.

    Returns:
        Dict with the name, YAML path, resolved entity ids, unknown entities and metadata.
    """
    doc, meta = read_user_file(file_path)
    ids, unknown = registry.select(doc)
    yaml_path = Path(users_config_dir) / f"{name}.yaml"
    _write_yaml(yaml_path, name, doc)

    if input_dir is not None:
        in_p = Path(input_dir)
        if in_p.is_dir() and (in_p / f"{name}_news.csv").exists() or (in_p / f"{name}.csv").exists() or in_p.name in ("subscriptions", "input"):
            unk_dir = in_p / "_unknown"
            unk_dir.mkdir(parents=True, exist_ok=True)
            unk_file = unk_dir / f"{name}_unknown.txt"
        else:
            unk_file = in_p / "_unknown.txt"

        if unknown:
            lines = [f"{cat}: {val} — không tìm thấy trong danh sách entity" for cat, val in unknown]
            unk_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif unk_file.exists():
            unk_file.unlink()
            
    return {"name": name, "yaml_path": str(yaml_path), "ids": ids,
            "unknown": unknown, "meta": meta}


def compile_all(input_root: str | Path | None = None, registry=None,
                *, users_config_dir: str | Path = USERS_CONFIG_DIR) -> list[dict]:
    """Scan every user subscription file and compile them in bulk.

    Args:
        input_root: Root directory of the user subscription files.
        registry: Shared EntityRegistry; loaded when None.
        users_config_dir: Destination directory of the YAML config.

    Returns:
        Compile result per user.
    """
    if registry is None:
        from src.agent.catalog.entities import load_registry
        registry = load_registry()
        
    if input_root is None:
        if DEFAULT_SUBSCRIPTIONS_ROOT.exists():
            input_root = DEFAULT_SUBSCRIPTIONS_ROOT
        elif LEGACY_INPUT_ROOT.exists():
            input_root = LEGACY_INPUT_ROOT
        else:
            input_root = DEFAULT_SUBSCRIPTIONS_ROOT
    input_root = Path(input_root)
    results: list[dict] = []
    processed_users: set[str] = set()

    if input_root.exists():
        flat_files = sorted(
            [p for p in input_root.iterdir() if p.is_file() and not p.name.startswith("_") and p.suffix.lower() in (".csv", ".xlsx", ".xlsm")],
            key=lambda p: (0 if p.suffix.lower() in (".xlsx", ".xlsm") else 1, p.name)
        )
        for p in flat_files:
            uname = _user_from_filename(p.name)
            if uname and uname not in processed_users:
                results.append(compile_user(uname, p, registry,
                                            users_config_dir=users_config_dir, input_dir=input_root))
                processed_users.add(uname)

        for d in sorted(p for p in input_root.iterdir() if p.is_dir()):
            if d.name.startswith("_") or d.name in processed_users:
                continue
            candidates = [d / "entities.csv", d / f"{d.name}_news.csv", d / f"{d.name}.csv", d / "entities.xlsx"]
            for target_file in candidates:
                if target_file.exists():
                    results.append(compile_user(d.name, target_file, registry,
                                                users_config_dir=users_config_dir, input_dir=d))
                    processed_users.add(d.name)
                    break

    try:
        from src.agent.catalog.entities import load_registry
        load_registry.cache_clear()
    except Exception:
        pass
    return results


# ---- user on/off manifest -----------------------------------------------------
def load_manifest(input_root: str | Path | None = None) -> dict[str, bool]:
    """Read manifest.yaml to determine which users are enabled.

    Args:
        input_root: Directory containing manifest.yaml.

    Returns:
        Mapping of user name to enabled state (True or False).
    """
    manifest = load_user_manifest(input_root)
    if not manifest["enabled"]:
        return {n: False for n in manifest["users"]}
    return manifest["users"]


def enabled_users(input_root: str | Path | None = None,
                  names: list[str] | None = None) -> set[str]:
    """Determine the set of user names enabled to receive news.

    Args:
        input_root: Root directory containing the manifest and subscription files.
        names: Candidate user names; when None they are discovered automatically.

    Returns:
        Names of the enabled users.
    """
    manifest = load_manifest(input_root)
    if names is None:
        names_found: set[str] = set()
        root = Path(input_root) if input_root else (
            DEFAULT_SUBSCRIPTIONS_ROOT if DEFAULT_SUBSCRIPTIONS_ROOT.exists() else LEGACY_INPUT_ROOT
        )
        if root.exists():
            for p in root.iterdir():
                if not p.name.startswith("_"):
                    if p.is_file() and p.suffix.lower() in (".csv", ".xlsx"):
                        names_found.add(_user_from_filename(p.name))
                    elif p.is_dir():
                        names_found.add(p.name)
        names = sorted(names_found | set(manifest))
    return {n for n in names if manifest.get(n, True)}

