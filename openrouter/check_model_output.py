import requests
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

api_key = ""
for l in Path("openrouter/.env").read_text(encoding="utf-8").splitlines():
    if l.startswith("OPENROUTER_API_KEY="):
        api_key = l.split("=", 1)[1].strip().strip("'\"")

# Test thử tắt reasoning hoặc để max_tokens lớn
payload = {
    "model": "stealth/space-bunny-alpha",
    "messages": [
        {"role": "user", "content": "Tóm tắt trong 1 câu: SCIC thông báo thoái vốn Nhựa Bình Minh."}
    ],
    "max_tokens": 1000,
}
resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    json=payload,
    headers={"Authorization": f"Bearer {api_key}"},
)
data = resp.json()
choice = data["choices"][0]
msg = choice["message"]
usage = data.get("usage", {})
print("Usage:", usage)
print("Finish reason:", choice.get("finish_reason"))
print("Content length:", len(msg.get("content") or ""))
print("Content:", msg.get("content"))
