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

for effort in ("low", "minimal", "0"):
    payload = {
        "model": "stealth/space-bunny-alpha",
        "messages": [{"role": "user", "content": "1+1=?"}],
        "reasoning": {"effort": effort},
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    print(f"Effort: {effort} -> Status: {resp.status_code}, Body: {resp.text[:200]}")
