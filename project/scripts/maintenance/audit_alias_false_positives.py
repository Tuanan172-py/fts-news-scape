"""Kiểm toán tần suất và rủi ro nhận diện sai của các bí danh ngắn."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "data" / "monocle.db"


def _bare_short_keys(reg, max_len: int) -> dict[str, list[str]]:
    """Alias index key (da fold) khong co dau cach va do dai <= max_len — nhom rui ro cao
    nhat: 1 am tiet/1 tu, de trung nghia voi tu thong dung khac hoac danh tu rieng ghep
    (xem docstring _context_guards.yaml)."""
    return {k: v for k, v in reg._alias_index.items() if " " not in k and len(k) <= max_len}


def _alias_shape(reg, eid: str, key: str) -> str:
    """Dang chinh ta cua alias sinh ra khop nay — de nguoi doc uu tien: alias ASCII khong
    dau, khong viet hoa toan phan giong het 1 tu dien thong dung nen rui ro cao nhat (kieu
    "Trang"); alias co dau tieng Viet rui ro trung danh tu rieng ghep (kieu "Mỹ" ăn theo "Mỹ
    Thuận"); ky hieu ASCII viet hoa (US, EU, DXY) it rui ro nhat vi da bat buoc dung hoa."""
    forms = reg._alias_forms.get(key) or []
    shapes = set()
    for f in forms:
        if any(ord(c) > 127 for c in f):
            shapes.add("co-dau")
        elif f.isascii() and f.isupper():
            shapes.add("ky-hieu-HOA")
        else:
            shapes.add("tu-dien-thuong")
    return "+".join(sorted(shapes)) if shapes else "?"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Duong dan monocle.db")
    ap.add_argument("--max-len", type=int, default=6, help="Do dai toi da (sau fold) cua alias 1-tu can soi")
    ap.add_argument("--min-hits", type=int, default=2, help="Chi bao cao entity co >= so lan khop nay")
    ap.add_argument("--examples", type=int, default=6, help="So vi du tieu de in ra moi entity")
    ap.add_argument("--out", default=None, help="Ghi bao cao ra file thay vi in stdout")
    args = ap.parse_args(argv)

    from src.agent.entities import load_registry

    reg = load_registry()
    bare_short = _bare_short_keys(reg, args.max_len)

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    cur.execute("SELECT title FROM articles WHERE title IS NOT NULL AND title != ''")
    titles = [r[0] for r in cur.fetchall()]

    hit_counter: Counter[str] = Counter()
    surfaces: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[str]] = defaultdict(list)

    for title in titles:
        for d in reg.detect(title):
            if d["via"] != "alias":
                continue
            surf = d.get("surface") or ""
            from src.agent.entities import _fold
            if _fold(surf) not in bare_short:
                continue
            eid = d["entity_id"]
            hit_counter[eid] += 1
            surfaces[eid].add(surf)
            if len(examples[eid]) < args.examples:
                examples[eid].append(title)

    lines = [
        f"Tong tieu de quet: {len(titles)}",
        f"Alias 1-tu (<= {args.max_len} ky tu sau fold) trong index: {len(bare_short)}",
        "",
    ]
    for eid, cnt in hit_counter.most_common():
        if cnt < args.min_hits:
            continue
        e = reg.entities[eid]
        # tim key alias tuong ung de bao cao dang chinh ta
        key = next((k for k, v in bare_short.items() if eid in v), "?")
        shape = _alias_shape(reg, eid, key)
        lines.append(f"{cnt:5d}  {eid:32s} dang={shape:16s} surfaces={sorted(surfaces[eid])!r}"
                     f"  ten={e['canonical_name']}")
        for t in examples[eid]:
            lines.append(f"         - {t}")
        lines.append("")

    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"Da ghi bao cao: {args.out} ({len(lines)} dong)")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
