"""
compile_users.py — Biên dịch input Excel của user → config yaml subscription.

Quét users/input/<name>/entities.xlsx → project/config/entities/users/<name>.yaml.
Báo entity không map được (users/input/<name>/_unknown.txt) mà KHÔNG làm hỏng compile.

Usage:
    python scripts/compile_users.py --all
    python scripts/compile_users.py --input-root ../users/input
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.users.compile import (                       # noqa: E402
    DEFAULT_INPUT_ROOT, compile_all, enabled_users,
)

force_utf8_stdio()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    ap.add_argument("--all", action="store_true", help="(mặc định) compile mọi user folder")
    args = ap.parse_args(argv)

    results = compile_all(args.input_root)
    on = enabled_users(args.input_root)
    if not results:
        print(f"Không thấy user nào trong {args.input_root} (cần <name>/entities.xlsx)")
        return 0
    for r in results:
        flag = "BẬT " if r["name"] in on else "tắt "
        n_unknown = len(r["unknown"])
        extra = f" | {n_unknown} entity không map (xem _unknown.txt)" if n_unknown else ""
        print(f"[{flag}] {r['name']}: {len(r['ids'])} entity → {r['yaml_path']}{extra}")
    print(f"\ncompiled={len(results)} users; enabled={sorted(on)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
