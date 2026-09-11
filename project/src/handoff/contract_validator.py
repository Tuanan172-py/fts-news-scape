"""Bộ kiểm định cấu trúc dữ liệu JSON theo lược đồ hợp đồng JSON Schema.

Cung cấp các hàm tải schema và xác thực đối tượng dữ liệu hoặc tệp tin JSON
theo chuẩn Draft 2020-12.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Thư mục chứa các lược đồ mặc định
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
KNOWN_SCHEMAS = {
    "work-package-v1": SCHEMAS_DIR / "work-package-v1.schema.json",
    "agent-output-v1": SCHEMAS_DIR / "agent-output-v1.schema.json",
    "silver-v1": SCHEMAS_DIR / "silver-v1.schema.json",
    "l1-entity-output-v1": SCHEMAS_DIR / "l1-entity-output-v1.schema.json",
}


def load_schema(name_or_path: str) -> dict:
    """Tải nội dung lược đồ JSON từ tên định danh hoặc đường dẫn tệp.

    Args:
        name_or_path: Tên lược đồ đã biết hoặc đường dẫn tới tệp schema JSON.

    Returns:
        Đối tượng từ điển chứa nội dung lược đồ JSON.
    """
    p = KNOWN_SCHEMAS.get(name_or_path, Path(name_or_path))
    return json.loads(Path(p).read_text(encoding="utf-8"))


def validate(instance: dict, schema: dict | str) -> tuple[bool, list[str]]:
    """Kiểm tra tính hợp lệ của đối tượng dữ liệu JSON theo lược đồ chỉ định.

    Args:
        instance: Dữ liệu JSON cần kiểm tra tính hợp lệ.
        schema: Từ điển lược đồ hoặc tên/đường dẫn lược đồ JSON.

    Returns:
        Tuple gồm cờ thành công (True/False) và danh sách chuỗi mô tả lỗi vi phạm.
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
    """Đọc tệp dữ liệu JSON và kiểm tra tính hợp lệ theo lược đồ chỉ định.

    Args:
        instance_path: Đường dẫn tệp JSON cần kiểm tra.
        schema_name_or_path: Tên lược đồ hoặc đường dẫn tệp schema.

    Returns:
        Tuple gồm cờ thành công (True/False) và danh sách chuỗi lỗi vi phạm.
    """
    instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    return validate(instance, load_schema(schema_name_or_path))


def main(argv: list[str]) -> int:
    """Điểm nhập thực thi dòng lệnh của công cụ kiểm định hợp đồng JSON."""
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
