"""Dieu phoi va gui cac Mega-Batch toi OpenRouter API stealth/space-bunny-alpha de xu ly bai dang."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Dam bao encoding UTF-8 tren Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

import requests

PACKETS_DIR = _CURRENT_DIR / "packets"
OUTPUTS_DIR = _CURRENT_DIR / "outputs"
DEFAULT_MODEL = "stealth/space-bunny-alpha"


def load_env_key() -> str:
    """Doc API key tu bien moi truong hoac openrouter/.env."""
    env_file = _CURRENT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return os.getenv("OPENROUTER_API_KEY", "")


SYSTEM_PROMPT = (
    "Ban la Chuyen vien Phan tich Tai chinh va Du lieu cao cap cua he thong News-Scape.\n"
    "Doc danh sach cac bai bao tai chinh trong packet va phan tich tung bai.\n"
    "BAT BUOC: Tra ve DUY NHAT mot mang JSON (JSON Array), moi phan tu co dung schema sau:\n"
    "[\n"
    "  {\n"
    '    "i": 0,\n'
    '    "s": "Tom tat noi dung va ban chat tai chinh cua su kien trong 1-2 cau ngan gon (duoi 50 tu).",\n'
    '    "sn": "pos" | "neg" | "neu",\n'
    '    "ms": 0.85,\n'
    '    "k": ["Luan diem chinh 1", "Luan diem chinh 2"],\n'
    '    "c": [0, 1]\n'
    "  }\n"
    "]\n"
    "RANG BUOC BAT BIEN:\n"
    "1. 'i': Chi so bai viet tuong ung voi chi so 'i' trong packet.\n"
    "2. 'sn' (sentiment): Chi duoc phep la 'pos', 'neg', hoac 'neu'.\n"
    "3. 'ms' (materiality_score): So thuc tu 0.0 den 1.0 phan anh muc do trong yeu tai chinh.\n"
    "4. 'k' (key_points): Mang chuoi luan diem dien giai rieng, khong copy nguyen van trich dan.\n"
    "5. 'c' (citations): Mang so nguyen chi dinh so thu tu cac doan van ban (p) chua chung cu (vd: [0, 1]).\n"
    "YEU CAU: SUC TICH, khong viet dai dong, duoi 150 token moi bai. Khong them bat ky chu dan nao ngoai mang JSON."
)


def send_batch_to_openrouter(
    api_key: str,
    model: str,
    packet_json_str: str,
    timeout: int = 180,
) -> tuple[int, str, dict[str, Any], float]:
    """Gui payload cua ca lo bai viet toi OpenRouter va ghi nhan thoi gian phan hoi."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Tuanan172-py/fts-news-scape",
        "X-Title": "News-Scape Batch Processor",
    }
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": packet_json_str},
        ],
        "reasoning": {"effort": "minimal"},
        "temperature": 0.1,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        elapsed = time.perf_counter() - start
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            return 200, content, usage, elapsed
        return resp.status_code, resp.text, {}, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return -1, str(exc), {}, elapsed


def validate_batch_output(raw_output: str, expected_count: int) -> tuple[bool, list[dict[str, Any]], str]:
    """Kiem tra tinh hop le cua mang JSON ket qua tra ve tu mo hinh."""
    if not raw_output:
        return False, [], "Du lieu phan hoi rong"

    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, [], f"Loi giai ma JSON: {e}"

    if isinstance(data, dict):
        for key in ("items", "articles", "results", "data"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break

    if not isinstance(data, list):
        return False, [], "Du lieu tra ve khong phai la mang JSON (Array)"

    valid_records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        summary = item.get("s")
        sentiment = item.get("sn")
        score = item.get("ms")
        key_points = item.get("k")
        citations = item.get("c")

        if idx is None or not isinstance(summary, str):
            continue
        if sentiment not in ("pos", "neg", "neu"):
            sentiment = "neu"
        if not isinstance(score, (int, float)):
            score = 0.5
        score = max(0.0, min(1.0, float(score)))

        if not isinstance(key_points, list):
            key_points = [summary]
        if not isinstance(citations, list):
            citations = [0]

        valid_records.append({
            "i": idx,
            "summary": summary,
            "sentiment": sentiment,
            "materiality_score": score,
            "key_points": key_points,
            "citations": citations,
        })

    is_full = len(valid_records) >= int(expected_count * 0.8)
    note = f"Nhan {len(valid_records)}/{expected_count} ban ghi hop le"
    return is_full, valid_records, note


def process_single_batch(
    batch_meta: dict[str, Any],
    api_key: str,
    model: str,
    skip_existing: bool = True,
) -> bool:
    """Xu ly mot lo duy nhat: doc packet, goi API, luu ket qua co checkpoint."""
    batch_id = batch_meta["batch_id"]
    task_file = PACKETS_DIR / batch_meta["task_file"]
    out_file = OUTPUTS_DIR / f"{batch_id}.output.json"

    if not task_file.exists():
        print(f"[!] Khong tim thay tep packet: {task_file}")
        return False

    expected_items = batch_meta["articles_count"]

    # Checkpoint: Bo qua neu da co ket qua hop le tu truoc
    if skip_existing and out_file.exists():
        try:
            cached_text = out_file.read_text(encoding="utf-8")
            is_ok, records, _ = validate_batch_output(cached_text, expected_items)
            if is_ok:
                print(f"[CHECKPOINT] {batch_id} da co ket qua hop le ({len(records)}/{expected_items} bai). Bo qua.")
                return True
        except Exception:
            pass

    packet_str = task_file.read_text(encoding="utf-8")
    print(f"\n>>> Dang xu ly {batch_id} ({expected_items} bai, Tier 1: {batch_meta['tier1_count']})...")

    # Thu toi da 2 lan neu gap loi mang
    for attempt in range(1, 3):
        status, raw_res, usage, latency = send_batch_to_openrouter(
            api_key=api_key,
            model=model,
            packet_json_str=packet_str,
        )

        if status == 200:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            out_file.write_text(raw_res, encoding="utf-8")

            is_ok, records, note = validate_batch_output(raw_res, expected_items)
            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)
            total_tok = usage.get("total_tokens", prompt_tok + comp_tok)

            status_tag = "[PASS]" if is_ok else "[PARTIAL]"
            print(f"  {status_tag} {note} trong {latency:.2f}s | Tokens: {total_tok} (Prompt: {prompt_tok}, Out: {comp_tok})")
            return is_ok

        print(f"  [CANH BAO] Lan thu {attempt} gap loi HTTP {status}: {raw_res[:150]}")
        if attempt < 2:
            time.sleep(3.0)

    return False


def main() -> None:
    """Diem vao thuc thi dieu phoi batch."""
    parser = argparse.ArgumentParser(description="Dieu phoi xu ly cac Mega-Batch bang OpenRouter API")
    parser.add_argument("--batch", type=int, default=None, help="So thu tu lo can chay (1-24)")
    parser.add_argument("--all", action="store_true", help="Chay toan bo cac lo trong manifest")
    parser.add_argument("--tier1-only", action="store_true", help="Chi chay cac lo Tier 1 (Watchlist)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Mo hinh su dung (mac dinh: {DEFAULT_MODEL})")
    parser.add_argument("--force", action="store_true", help="Chay lai ca nhung lo da co file output")
    args = parser.parse_args()

    manifest_file = PACKETS_DIR / "manifest.json"
    if not manifest_file.exists():
        print("[!] Chua tim thay manifest.json. Vui long chay `pack_today.py` truoc.")
        sys.exit(1)

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    batches = manifest.get("batches", [])
    api_key = load_env_key()

    if not api_key:
        print("[!] Khong tim thay OPENROUTER_API_KEY trong openrouter/.env")
        sys.exit(1)

    skip_existing = not args.force

    if args.tier1_only:
        tier1_batches = [b for b in batches if b.get("tier1_count", 0) > 0]
        print(f"=== KICH HOAT GIAI DOAN 1: TIER 1 WATCHLIST ({len(tier1_batches)} LO) ===")
        success = sum(1 for b in tier1_batches if process_single_batch(b, api_key, args.model, skip_existing))
        print(f"\n[HOAN TAT TIER 1] {success}/{len(tier1_batches)} lo thanh cong.")
    elif args.all:
        print(f"=== KICH HOAT TOAN BO {len(batches)} LO NGAY 2026-09-29 ===")
        success = 0
        for idx, b in enumerate(batches, 1):
            ok = process_single_batch(b, api_key, args.model, skip_existing)
            if ok:
                success += 1
            time.sleep(2.0)
        print(f"\n[HOAN TAT TOAN BO] {success}/{len(batches)} lo thanh cong.")
    elif args.batch is not None:
        target_idx = args.batch - 1
        if 0 <= target_idx < len(batches):
            process_single_batch(batches[target_idx], api_key, args.model, skip_existing)
        else:
            print(f"[!] Chi so lo khong hop le: {args.batch} (Chi co {len(batches)} lo).")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
