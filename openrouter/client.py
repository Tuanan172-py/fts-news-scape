"""Quan ly ket noi va gui yeu cau suy luan qua 9Router Gateway hoac OpenRouter truc tiep."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Bao dam duong dan module luon tim thay schemas
_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

try:
    from openrouter.schemas import StructuredAnalysis, validate_structured_output
except ImportError:
    from schemas import StructuredAnalysis, validate_structured_output

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

import requests

DEFAULT_GATEWAY_URL = "http://localhost:20128/v1"
DIRECT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_STEALTH_MODEL = "stealth/space-bunny-alpha"


class SimpleGatewayClient:
    """Client suy luan thong qua HTTP POST su dung thu vien requests."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:20128",
            "X-Title": "News-Scape Automation",
        }

    def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> str:
        """Gui yeu cau chat completion va tra ve noi dung thoi gian thuc."""
        endpoint = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        resp = requests.post(
            endpoint,
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""


def get_router_client(
    base_url: str | None = None,
    api_key: str | None = None,
) -> Any:
    """Khoi tao phien ket noi client toi cong dieu phoi 9Router hoac OpenRouter."""
    target_url = base_url or os.getenv("ROUTER_BASE_URL", DEFAULT_GATEWAY_URL)
    target_key = (
        api_key
        or os.getenv("ROUTER_API_KEY")
        or os.getenv("OPENROUTER_API_KEY", "sk-9router-local")
    )

    if HAS_OPENAI:
        return OpenAI(
            base_url=target_url,
            api_key=target_key,
            default_headers={
                "HTTP-Referer": "http://localhost:20128",
                "X-Title": "News-Scape Automation",
            },
        )
    return SimpleGatewayClient(base_url=target_url, api_key=target_key)


def request_structured_completion(
    prompt: str,
    system_prompt: str | None = None,
    model: str = DEFAULT_STEALTH_MODEL,
    client: Any | None = None,
) -> StructuredAnalysis | None:
    """Gui yeu cau suy luan va kiem dinh tinh hop le cua schema dau ra."""
    active_client = client or get_router_client()
    default_sys = (
        "Ban la chuyen vien phan tich du lieu. "
        "BAT BUOC tra ve duy nhat 1 JSON object hop le theo cau truc: "
        '{"summary": str, "sentiment": "pos"|"neg"|"neu", "materiality_score": float, "key_points": [str]}. '
        "Khong them bat ky loi dan hoac ky tu thua ngoai JSON."
    )
    messages = [
        {"role": "system", "content": system_prompt or default_sys},
        {"role": "user", "content": prompt},
    ]

    try:
        if HAS_OPENAI and isinstance(active_client, OpenAI):
            response = active_client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0.1,
            )
            raw_text = response.choices[0].message.content or ""
        elif hasattr(active_client, "chat_completion"):
            raw_text = active_client.chat_completion(
                model=model,
                messages=messages,
                temperature=0.1,
            )
        else:
            return None
    except Exception as exc:
        print(f"Loi ket noi toi endpoint: {exc}")
        return None

    return validate_structured_output(raw_text)
