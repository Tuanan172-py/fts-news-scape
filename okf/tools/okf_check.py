#!/usr/bin/env python3
"""okf-check — phát hiện KB OKF lạc hậu so với code nguồn (LOCAL-FIRST, no GCP).

Quét okf/catalog/**/*.md, đọc frontmatter `sources[].resource` + `sources_last_checked`,
so ngày thay đổi gần nhất của mỗi file nguồn (git commit-time, fallback fs-mtime) với
`sources_last_checked`. File OKF stale nếu nguồn đổi SAU last-checked.

Usage (chạy bằng project venv có PyYAML):
    "project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated [--all] [--json] [--no-git]

Exit code: 0 = mọi OKF up-to-date · 1 = có file stale · 2 = lỗi cấu hình.
Dùng làm pre-commit/CI gate ở GĐ2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    sys.stderr.write(
        "[okf-check] Thiếu PyYAML. Chạy bằng project venv:\n"
        '  "project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated\n'
    )
    sys.exit(2)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = REPO_ROOT / "okf" / "catalog"
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str | None]:
    """Return (frontmatter_dict, error). error != None nếu có block --- nhưng YAML hỏng."""
    m = FM_RE.match(text)
    if not m:
        return {}, None
    try:
        data = yaml.safe_load(m.group(1))
        if isinstance(data, dict):
            return data, None
        return {}, "frontmatter không phải mapping"
    except yaml.YAMLError as e:
        msg = str(getattr(e, "problem", e) or e).splitlines()[0][:80]
        return {}, f"YAML lỗi: {msg}"


def clean_resource(value: str) -> str | None:
    """'project/data/monocle.db (table: articles)' -> 'project/data/monocle.db'."""
    if not isinstance(value, str):
        return None
    token = re.split(r"[\s(]", value.strip(), maxsplit=1)[0]
    return token or None


def collect_sources(fm: dict) -> list[Path]:
    """Path (tồn tại, dưới repo) từ mỗi `sources[].resource`.

    CHỦ Ý bỏ `resource` top-level: đó là TÀI SẢN được mô tả (vd file .db đổi mỗi crawl),
    không phải căn cứ tri thức. Staleness chỉ đo theo `sources[]` (code/doc authorities).
    """
    raw: list[str] = []
    for s in fm.get("sources", []) or []:
        if isinstance(s, dict):
            r = clean_resource(s.get("resource", ""))
            if r:
                raw.append(r)
    out: list[Path] = []
    for r in raw:
        p = (REPO_ROOT / r)
        if p.is_file():
            out.append(p)
    return out


def to_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(s).date()
        except ValueError:
            try:
                return dt.date.fromisoformat(s[:10])
            except ValueError:
                return None
    return None


def last_checked_date(fm: dict) -> dt.date | None:
    d = to_date(fm.get("sources_last_checked"))
    if d:
        return d
    gen = fm.get("generated")
    if isinstance(gen, dict):
        return to_date(gen.get("at"))
    return None


def git_commit_date(path: Path) -> dt.date | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
        )
        line = out.stdout.strip()
        if line:
            return dt.datetime.fromisoformat(line.replace("Z", "+00:00")).date()
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return None


def source_change_date(path: Path, use_git: bool) -> dt.date | None:
    if use_git:
        d = git_commit_date(path)
        if d:
            return d
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


def check(use_git: bool) -> list[dict]:
    rows: list[dict] = []
    for md in sorted(CATALOG.rglob("*.md")):
        if md.name == "index.md":
            continue  # index = điều hướng, không có nguồn code trực tiếp
        fm, err = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        rel = md.relative_to(REPO_ROOT).as_posix()
        if err:
            rows.append({"file": rel, "status": "parse-error", "last_checked": None,
                         "newest_source_date": None, "newest_source": err, "n_sources": 0})
            continue
        if not fm:
            continue  # không có frontmatter (vd file prose thuần)
        checked = last_checked_date(fm)
        sources = collect_sources(fm)
        newest = None
        newest_src = None
        for s in sources:
            d = source_change_date(s, use_git)
            if d and (newest is None or d > newest):
                newest, newest_src = d, s
        rel = md.relative_to(REPO_ROOT).as_posix()
        if not sources:
            status = "no-source"
        elif checked is None:
            status = "no-checked-date"
        elif newest and newest > checked:
            status = "stale"
        else:
            status = "ok"
        rows.append({
            "file": rel,
            "status": status,
            "last_checked": checked.isoformat() if checked else None,
            "newest_source_date": newest.isoformat() if newest else None,
            "newest_source": newest_src.relative_to(REPO_ROOT).as_posix() if newest_src else None,
            "n_sources": len(sources),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(prog="okf-check")
    ap.add_argument("command", choices=["outdated"], help="kiểm tra KB lạc hậu")
    ap.add_argument("--all", action="store_true", help="in mọi file, không chỉ stale")
    ap.add_argument("--json", action="store_true", help="xuất JSON")
    ap.add_argument("--no-git", action="store_true", help="dùng fs-mtime thay git commit-time")
    args = ap.parse_args()

    if not CATALOG.is_dir():
        sys.stderr.write(f"[okf-check] Không thấy {CATALOG}\n")
        return 2

    rows = check(use_git=not args.no_git)
    stale = [r for r in rows if r["status"] == "stale"]
    perr = [r for r in rows if r["status"] == "parse-error"]
    warn = [r for r in rows if r["status"] in ("no-source", "no-checked-date")]
    fail = stale + perr  # gate: stale hoặc frontmatter hỏng → exit 1

    if args.json:
        print(json.dumps({"rows": rows, "stale": len(stale), "parse_error": len(perr)},
                         ensure_ascii=False, indent=2))
        return 1 if fail else 0

    shown = rows if args.all else (fail + warn)
    if shown:
        print(f"{'STATUS':<16} {'LAST_CHECKED':<12} {'NEWEST_SRC':<12} FILE")
        order = {"stale": 0, "parse-error": 1}
        for r in sorted(shown, key=lambda x: (order.get(x["status"], 2), x["file"])):
            note = ""
            if r["status"] == "stale":
                note = f"  <- {r['newest_source']}"
            elif r["status"] == "parse-error":
                note = f"  ({r['newest_source']})"
            print(f"{r['status']:<16} {str(r['last_checked'] or '-'):<12} "
                  f"{str(r['newest_source_date'] or '-'):<12} {r['file']}{note}")
    print(f"\n[okf-check] {len(rows)} OKF file | stale={len(stale)} "
          f"| parse-error={len(perr)} | warn={len(warn)} "
          f"| ok={len(rows)-len(fail)-len(warn)} "
          f"| mode={'git' if not args.no_git else 'fs-mtime'}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
