"""
contract_validator — validate 1 instance JSON vs 1 JSON Schema (jsonschema).

DRY: 1 validator dùng cho CẢ work-package (producer gate) LẪN agent-output (khi agent
land). Không exec code. CLI + import. Xem phase-03/04/06.

Usage:
    python -m src.handoff.contract_validator <instance.json> <schema.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# thư mục schemas mặc định (project/schemas)
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
KNOWN_SCHEMAS = {
    "work-package-v1": SCHEMAS_DIR / "work-package-v1.schema.json",
    "agent-output-v1": SCHEMAS_DIR / "agent-output-v1.schema.json",
    "silver-v1": SCHEMAS_DIR / "silver-v1.schema.json",
}


def load_schema(name_or_path: str) -> dict:
    p = KNOWN_SCHEMAS.get(name_or_path, Path(name_or_path))
    return json.loads(Path(p).read_text(encoding="utf-8"))


def validate(instance: dict, schema: dict | str) -> tuple[bool, list[str]]:
    """Trả (ok, errors). errors = list message rỗng nếu hợp lệ."""
    from jsonschema import Draft202012Validator

    if isinstance(schema, str):
        schema = load_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return True, []
    msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors]
    return False, msgs


def validate_file(instance_path: str, schema_name_or_path: str) -> tuple[bool, list[str]]:
    instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    return validate(instance, load_schema(schema_name_or_path))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: contract_validator <instance.json> <schema.json|schema-name>")
        return 2
    ok, errors = validate_file(argv[0], argv[1])
    if ok:
        print(f"PASS: {argv[0]} valid vs {argv[1]}")
        return 0
    print(f"FAIL: {argv[0]} invalid vs {argv[1]}")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
