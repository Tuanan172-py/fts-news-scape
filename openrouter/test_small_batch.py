import json
import os
import sys
import time
from pathlib import Path
import requests

_CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CURRENT_DIR))

from process_batches import SYSTEM_PROMPT, validate_batch_output

env_file = _CURRENT_DIR / ".env"
api_key = ""
for l in env_file.read_text(encoding="utf-8").splitlines():
    if l.startswith("OPENROUTER_API_KEY="):
        api_key = l.split("=", 1)[1].strip().strip("'\"")

task_file = _CURRENT_DIR / "packets" / "batch_20260929_01.task.json"
data = json.loads(task_file.read_text(encoding="utf-8"))

# Test với 5 bài viết đầu tiên
sample_size = 5
small_packet = {
    "date": data["date"],
    "batch_id": f"test_small_{sample_size}",
    "total_items": sample_size,
    "articles": data["articles"][:sample_size],
}

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/Tuanan172-py/fts-news-scape",
    "X-Title": "News-Scape Test Small",
}

payload = {
    "model": "stealth/space-bunny-alpha",
    "response_format": {"type": "json_object"},
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(small_packet, ensure_ascii=False)},
    ],
    "temperature": 0.1,
}

print(f"[*] Dang gui lo thu nghiem {sample_size} bai toi OpenRouter...")
t0 = time.perf_counter()
resp = requests.post(url, json=payload, headers=headers, timeout=120)
elapsed = time.perf_counter() - t0

print(f"[*] Ket qua: HTTP {resp.status_code} trong {elapsed:.2f} giay.")
if resp.status_code == 200:
    data_res = resp.json()
    content = data_res["choices"][0]["message"]["content"]
    usage = data_res.get("usage", {})
    print(f"[*] Tokens: {usage}")
    is_ok, records, note = validate_batch_output(content, sample_size)
    print(f"[*] Kiem dinh Schema: {is_ok} ({note})")
    print("[*] Mau ket qua bai dau tien:")
    if records:
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
else:
    print(f"[!] Loi: {resp.text[:300]}")
