"""Validate JSON data against contract JSON Schemas (Draft 2020-12), loading schemas by name or path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Directory that holds the default schemas.
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
KNOWN_SCHEMAS = {
    "work-package-v1": SCHEMAS_DIR / "work-package-v1.schema.json",
    "agent-output-v1": SCHEMAS_DIR / "agent-output-v1.schema.json",
    "agent-output-v2-lean": SCHEMAS_DIR / "agent-output-v2-lean.schema.json",
    "silver-v1": SCHEMAS_DIR / "silver-v1.schema.json",
    "l1-entity-output-v1": SCHEMAS_DIR / "l1-entity-output-v1.schema.json",
}


def load_schema(name_or_path: str) -> dict:
    """Load a JSON schema from a known name or a file path.

    Args:
        name_or_path: Known schema name or path to a JSON schema file.

    Returns:
        Dict with the JSON schema content.
    """
    p = KNOWN_SCHEMAS.get(name_or_path, Path(name_or_path))
    return json.loads(Path(p).read_text(encoding="utf-8"))


def validate(instance: dict, schema: dict | str) -> tuple[bool, list[str]]:
    """Validate a JSON data object against the given schema.

    Args:
        instance: JSON data to validate.
        schema: Schema dict, or the name or path of a JSON schema.

    Returns:
        Tuple of a success flag and the list of violation messages.
    """
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
    """Read a JSON data file and validate it against the given schema.

    Args:
        instance_path: Path of the JSON file to validate.
        schema_name_or_path: Schema name or path of the schema file.

    Returns:
        Tuple of a success flag and the list of violation messages.
    """
    instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    return validate(instance, load_schema(schema_name_or_path))


def main(argv: list[str]) -> int:
    """Run the command-line entry point of the JSON contract validator.

    Args:
        argv: Command-line arguments: the instance JSON path and the schema name or path.

    Returns:
        Exit code: 0 when valid, 1 when invalid, 2 on a usage error.
    """
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
