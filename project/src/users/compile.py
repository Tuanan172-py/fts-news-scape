"""
compile.py — Biên dịch input NGƯỜI DÙNG (Excel) → config subscription (yaml).

Người dùng chỉ nhập 1 file `entities.xlsx` đơn giản trong `users/input/<name>/`. Hệ thống:
  * đọc sheet `entities` (mỗi cột = 1 nhóm: tickers/etfs/indices/exchanges/industries/entities),
  * validate qua EntityRegistry.select() (map + báo entity không tìm thấy),
  * sinh `project/config/entities/users/<name>.yaml` (định dạng máy đọc, người dùng KHÔNG đụng),
  * ghi `users/input/<name>/_unknown.txt` nếu có giá trị không map được.

Bật/tắt user đọc từ `users/input/manifest.yaml` (vắng tên = mặc định BẬT).

Không phát minh logic map — mọi ánh xạ dùng lại `EntityRegistry.select()` (entities.py).
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
import yaml

# src/users/compile.py → parents[2] = project/ ; repo root = project/..
# src/users/compile.py → parents[2] = project/ ; repo root = project/..
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_SUBSCRIPTIONS_ROOT = REPO_ROOT / "users" / "subscriptions"
DEFAULT_INPUT_ROOT = DEFAULT_SUBSCRIPTIONS_ROOT if DEFAULT_SUBSCRIPTIONS_ROOT.exists() else (REPO_ROOT / "users" / "input")
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "users" / "output"
USERS_CONFIG_DIR = PROJECT_ROOT / "config" / "entities" / "users"

# Nhóm hợp lệ trong sheet `entities` — khớp đúng key của EntityRegistry.select().
GROUP_KEYS = ("tickers", "etfs", "indices", "exchanges", "industries", "nations", "themes", "macro", "assets", "institutions", "entities")
# Nhóm dùng MÃ (in hoa) — chuẩn hoá để khớp entity_id (code uppercase trong entities.json).
_UPPER_GROUPS = ("tickers", "etfs", "indices", "exchanges", "industries", "nations", "themes", "macro", "assets", "institutions")


def _user_from_filename(filename: str) -> str:
    """Tách username từ tên file: 'AnPT_news.csv' -> 'AnPT', 'AnPT.csv' -> 'AnPT'."""
    stem = Path(filename).stem
    if stem.lower().endswith("_news"):
        return stem[:-5]
    return stem


# ---- CSV & Excel I/O ----------------------------------------------------------
def read_user_csv(path: str | Path) -> tuple[dict, dict]:
    """Đọc file CSV đăng ký danh mục của user → (doc, meta).
    
    Hỗ trợ 2 định dạng:
    1. Định dạng Ma trận ngang (Horizontal): Header gồm các nhóm (tickers, industries, themes...).
    2. Định dạng Tidy dọc (Vertical): Header gồm 'category'/'type' và 'code'/'value' (tùy chọn 'note').
    """
    import csv
    path = Path(path)
    doc: dict[str, list[str]] = {}
    meta: dict = {"user": _user_from_filename(path.name)}
    
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        # Bỏ qua các dòng comment (#) ở đầu file nếu có
        lines = [line for line in f if line.strip() and not line.strip().startswith("#")]
    
    if not lines:
        return _normalize(doc), meta

    # Tự động nhận diện dấu phân cách (hỗ trợ comma, tab, semicolon)
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
    
    # Kiểm tra kiểu Vertical (category, code)
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
        # Kiểu Horizontal (mỗi cột là 1 nhóm)
        col_idx = {h: i for i, h in enumerate(headers) if h in GROUP_KEYS}
        for r in rows[1:]:
            for key, idx in col_idx.items():
                if idx < len(r) and r[idx].strip():
                    doc.setdefault(key, []).append(r[idx].strip())

    return _normalize(doc), meta


def write_user_csv(path: str | Path, doc: dict, meta: dict | None = None) -> Path:
    """Ghi danh mục user ra file CSV (dạng horizontal ma trận ngang)."""
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
    """Đọc file Excel subscription của user → (doc, meta).
    
    Quy tắc:
    - User chỉ cần điền DUY NHẤT 1 sheet đầu tiên (chứa danh sách tickers/industries...).
    - Username được tự động suy ra từ tên file ({username}_news.xlsx hoặc {username}.xlsx).
    - Không bắt buộc và không yêu cầu user phải tạo hay điền sheet meta.
    """
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    doc: dict[str, list[str]] = {}
    
    # Ưu tiên sheet đầu tiên (hoặc sheet tên 'entities'/'subscriptions')
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

    # Username tự động lấy từ tên file
    meta: dict = {"user": _user_from_filename(path.name)}
    if "meta" in wb.sheetnames:
        for r in wb["meta"].iter_rows(values_only=True):
            if not r or not r[0]:
                continue
            key = str(r[0]).strip().lower()
            if key == "key":            # bỏ dòng tiêu đề key/value
                continue
            meta[key] = r[1] if len(r) > 1 else None
    wb.close()
    return _normalize(doc), meta


def write_user_xlsx(path: str | Path, doc: dict, meta: dict | None = None) -> Path:
    """Ghi subscription ra file XLSX (sheet chính là entities, cột = GROUP_KEYS)."""
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
    """Tự động nhận diện định dạng file (.csv hoặc .xlsx) và đọc (doc, meta)."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return read_user_csv(p)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        return read_user_xlsx(p)
    raise ValueError(f"Không hỗ trợ định dạng file: {p.suffix}")


def _normalize(doc: dict) -> dict:
    """Chuẩn hoá: strip + upper cho nhóm dùng mã (gồm industries); giữ nguyên entities (entity_id)."""
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
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {k: doc[k] for k in GROUP_KEYS if doc.get(k)},
        allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    yaml_path.write_text(_YAML_HEADER.format(name=name) + body, encoding="utf-8")


def compile_user(name: str, file_path: str | Path, registry,
                 *, users_config_dir: str | Path = USERS_CONFIG_DIR,
                 input_dir: str | Path | None = None) -> dict:
    """Compile 1 user: file (csv/xlsx) → yaml (+ _unknown.txt). Trả record {name, yaml_path, ids, unknown}."""
    doc, meta = read_user_file(file_path)
    ids, unknown = registry.select(doc)
    yaml_path = Path(users_config_dir) / f"{name}.yaml"
    _write_yaml(yaml_path, name, doc)

    if input_dir is not None:
        in_p = Path(input_dir)
        # Nếu in_p là thư mục gốc subscriptions/ -> lưu vào subscriptions/_unknown/{name}_unknown.txt
        # Nếu in_p là thư mục riêng user (cũ) -> lưu vào in_p/_unknown.txt
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
            unk_file.unlink()  # sạch cảnh báo cũ khi user đã sửa
            
    return {"name": name, "yaml_path": str(yaml_path), "ids": ids,
            "unknown": unknown, "meta": meta}


def compile_all(input_root: str | Path | None = None, registry=None,
                *, users_config_dir: str | Path = USERS_CONFIG_DIR) -> list[dict]:
    """Quét mọi file đăng ký trong users/subscriptions/ (hoặc users/input/) → compile. Trả list record.

    Sau khi ghi yaml, xoá cache registry để lần load sau nạp subscription mới.
    """
    if registry is None:
        from src.agent.entities import load_registry
        registry = load_registry()
        
    if input_root is None:
        if DEFAULT_SUBSCRIPTIONS_ROOT.exists():
            input_root = DEFAULT_SUBSCRIPTIONS_ROOT
        elif (REPO_ROOT / "users" / "input").exists():
            input_root = REPO_ROOT / "users" / "input"
        else:
            input_root = DEFAULT_SUBSCRIPTIONS_ROOT
    input_root = Path(input_root)
    results: list[dict] = []
    processed_users: set[str] = set()

    if input_root.exists():
        # 1. Quét các file phẳng (*.xlsx, *.csv) trực tiếp trong thư mục subscriptions/ (ưu tiên .xlsx)
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

        # 2. Quét các thư mục con (hỗ trợ backward compatibility với cấu trúc cũ input/<name>/entities.xlsx)
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

    try:  # invalidate lru_cache để subscription mới có hiệu lực
        from src.agent.entities import load_registry
        load_registry.cache_clear()
    except Exception:
        pass
    return results


# ---- manifest bật/tắt user ----------------------------------------------------
def load_manifest(input_root: str | Path | None = None) -> dict[str, bool]:
    """Đọc manifest.yaml từ thư mục đăng ký (subscriptions hoặc input) → {name: enabled}."""
    if input_root is None:
        candidates = [
            DEFAULT_SUBSCRIPTIONS_ROOT / "manifest.yaml",
            REPO_ROOT / "users" / "input" / "manifest.yaml",
        ]
    else:
        candidates = [
            Path(input_root) / "manifest.yaml",
            DEFAULT_SUBSCRIPTIONS_ROOT / "manifest.yaml",
            REPO_ROOT / "users" / "input" / "manifest.yaml",
        ]

    for path in candidates:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            users = data.get("users") or {}
            return {str(k): bool(v) for k, v in users.items()}
    return {}


def enabled_users(input_root: str | Path | None = None,
                  names: list[str] | None = None) -> set[str]:
    """Tập user BẬT: manifest quyết định; vắng tên trong manifest = mặc định BẬT.

    `names` = danh sách user ứng viên. None → suy từ các file đăng ký và manifest keys.
    """
    manifest = load_manifest(input_root)
    if names is None:
        names_found: set[str] = set()
        root = Path(input_root) if input_root else (
            DEFAULT_SUBSCRIPTIONS_ROOT if DEFAULT_SUBSCRIPTIONS_ROOT.exists() else (REPO_ROOT / "users" / "input")
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

