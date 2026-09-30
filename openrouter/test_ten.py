import json
import requests
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CURRENT_DIR))

from process_batches import SYSTEM_PROMPT, validate_batch_output

api_key = ""
for l in (_CURRENT_DIR / ".env").read_text(encoding="utf-8").splitlines():
    if l.startswith("OPENROUTER_API_KEY="):
        api_key = l.split("=", 1)[1].strip().strip("'\"")

task_file = _CURRENT_DIR / "packets" / "batch_20260929_01.task.json"
data = json.loads(task_file.read_text(encoding="utf-8"))

# Test 10 bai voi reasoning effort minimal
ten_articles = data["articles"][:10]
small_packet = {
    "d": data["date"],
    "items": ten_articles,
}

payload = {
    "model": "stealth/space-bunny-alpha",
    "response_format": {"type": "json_object"},
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(small_packet, ensure_ascii=False)},
    ],
    "reasoning": {"effort": "minimal"},
    "temperature": 0.1,
}

print("[*] Gui thu nghiem 10 bai voi reasoning effort MINIMAL...")
t0 = time.perf_counter()
resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    json=payload,
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=150,
)
elapsed = time.perf_counter() - t0
print(f"[*] Status: {resp.status_code} trong {elapsed:.2f}s")

if resp.status_code == 200:
    res_data = resp.json()
    usage = res_data.get("usage", {})
    print("[*] Usage:", usage)
    content = res_data["choices"][0]["message"]["content"]
    is_ok, records, note = validate_batch_output(content, 10)
    print(f"[*] Kiem dinh: {is_ok} ({note})")
    if records:
        print("[*] Mau bai 1:", records[0]["summary"])
        print("[*] Mau bai cuoi:", records[-1]["summary"])
else:
    print("[!] Error:", resp.text[:300])
