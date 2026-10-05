import json
import sys
import time
from pathlib import Path
import requests

_CURRENT_DIR = Path(__file__).resolve().parent

env_file = _CURRENT_DIR / ".env"
api_key = ""
for l in env_file.read_text(encoding="utf-8").splitlines():
    if l.startswith("OPENROUTER_API_KEY="):
        api_key = l.split("=", 1)[1].strip().strip("'\"")

task_file = _CURRENT_DIR / "packets" / "batch_20260929_01.task.json"
data = json.loads(task_file.read_text(encoding="utf-8"))

# Test với 5 bài
sample_size = 5
small_packet = {
    "d": data["date"],
    "items": data["articles"][:sample_size],
}

SYSTEM_PROMPT = (
    "Ban la chuyen vien phan tich du lieu News-Scape.\n"
    "Doc danh sach bai bao va tra ve DUY NHAT 1 JSON Array:\n"
    "[\n"
    "  {\n"
    '    "i": 0,\n'
    '    "s": "Tom tat noi dung tai chinh ngan gon 1-2 cau (duoi 50 tu).",\n'
    '    "sn": "pos" | "neg" | "neu",\n'
    '    "ms": 0.8,\n'
    '    "k": ["Luan diem 1", "Luan diem 2"],\n'
    '    "c": [0, 1]\n'
    "  }\n"
    "]\n"
    "YEU CAU: SUC TICH, khong viet dai dong, duoi 150 token moi bai. Khong them bat ky chu dan nao ngoai mang JSON."
)

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/Tuanan172-py/fts-news-scape",
    "X-Title": "News-Scape Concise Test",
}

payload = {
    "model": "stealth/space-bunny-alpha",
    "response_format": {"type": "json_object"},
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(small_packet, ensure_ascii=False)},
    ],
    "max_tokens": 2000,
    "temperature": 0.1,
}

print(f"[*] Gui test {sample_size} bai voi yeu cau suc tich & max_tokens=2000...")
t0 = time.perf_counter()
resp = requests.post(url, json=payload, headers=headers, timeout=90)
elapsed = time.perf_counter() - t0
print(f"[*] Status: {resp.status_code} trong {elapsed:.2f} giay.")
if resp.status_code == 200:
    res_data = resp.json()
    usage = res_data.get("usage", {})
    print(f"[*] Tokens: {usage}")
    content = res_data["choices"][0]["message"]["content"]
    print(f"[*] Content length: {len(content)}")
    print(f"[*] Output preview: {content[:300]}")
else:
    print(f"[!] Error: {resp.text[:300]}")
