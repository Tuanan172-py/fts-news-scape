"""Kiem tra ket noi den 9Router Gateway va OpenRouter Stealth Models."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Them thu muc hien tai vao sys.path de chay duoc truc tiep hoac tu goc repo
_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))
_ROOT_DIR = _CURRENT_DIR.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

try:
    from openrouter.client import (
        DEFAULT_GATEWAY_URL,
        DEFAULT_STEALTH_MODEL,
        get_router_client,
        request_structured_completion,
    )
except ImportError:
    from client import (
        DEFAULT_GATEWAY_URL,
        DEFAULT_STEALTH_MODEL,
        get_router_client,
        request_structured_completion,
    )


def test_gateway_connection(model_name: str, base_url: str) -> bool:
    """Gui truy van mau kiem tra thoi gian dap ung va do tuong thich schema.

    Args:
        model_name: Dinh danh mo hinh can thu nghiem.
        base_url: Endpoint dich vu OpenAI-compatible.

    Returns:
        True neu phan hoi hop le va khop schema, False neu that bai.
    """
    print(f"[*] Dang kiem tra ket noi toi: {base_url}")
    print(f"[*] Mo hinh muc tieu: {model_name}")

    client = get_router_client(base_url=base_url)

    sample_prompt = (
        "Tong cong ty Dau tu va Kinh doanh von Nha nuoc (SCIC) thong bao ke hoach "
        "ban dau gia toan bo 36% co phan tai Cong ty Co phan Nhua Binh Minh voi muc gia "
        "khoi diem cao hon 15% so voi thi gia hien tai tren san HOSE."
    )

    start_time = time.perf_counter()
    result = request_structured_completion(
        prompt=sample_prompt,
        model=model_name,
        client=client,
    )
    elapsed = time.perf_counter() - start_time

    if result is None:
        print("[!] Ket noi that bai hoac phan hoi khong khop Schema JSON.")
        print("    Vui long kiem tra:")
        print("    1. Container 9Router da chay chua (docker ps).")
        print("    2. Provider OpenRouter / Gemini da duoc cau hinh API key tren dashboard (http://localhost:20128).")
        return False

    print(f"[+] Ket noi thanh cong trong {elapsed:.2f} giay.")
    print("[+] Ket qua sau khi qua cong kiem dinh Schema:")
    print(result.model_dump_json(indent=2))
    return True


def main() -> None:
    """Diem vao thuc thi script dong lenh."""
    parser = argparse.ArgumentParser(
        description="Kiem tra ket noi 9Router va OpenRouter Stealth Models"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_STEALTH_MODEL,
        help=f"Ten mo hinh kiem tra (mac dinh: {DEFAULT_STEALTH_MODEL})",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_GATEWAY_URL,
        help=f"Base URL gateway (mac dinh: {DEFAULT_GATEWAY_URL})",
    )
    args = parser.parse_args()

    success = test_gateway_connection(model_name=args.model, base_url=args.url)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
