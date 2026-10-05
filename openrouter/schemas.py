"""Dinh nghia cau truc du lieu va chot kiem dinh schema cho phan hoi tu LLM."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

try:
    from pydantic import BaseModel, Field, ValidationError
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


if HAS_PYDANTIC:
    class StructuredAnalysis(BaseModel):
        """Cau truc du lieu phan tich chuan cho tac vu xu ly van ban va tin tuc."""

        summary: str = Field(description="Tom tat ngan gon noi dung")
        sentiment: str = Field(
            pattern="^(pos|neg|neu)$",
            description="Sac thai: pos (tich cuc), neg (tieu cuc), neu (trung tinh)",
        )
        materiality_score: float = Field(
            ge=0.0,
            le=1.0,
            description="Thang diem trong yeu tai chinh 0.0 den 1.0",
        )
        key_points: list[str] = Field(
            min_length=1,
            description="Mang cac luan diem doc lap",
        )
else:
    @dataclass
    class StructuredAnalysis:
        """Cau truc du lieu phan tich chuan (che do dataclass fallback)."""

        summary: str
        sentiment: str
        materiality_score: float
        key_points: list[str]

        def model_dump_json(self, indent: int | None = None) -> str:
            """Xuat du lieu ra chuoi JSON dinh dang."""
            return json.dumps(asdict(self), ensure_ascii=False, indent=indent)


def extract_json_block(text: str) -> str:
    """Boc tach chuoi JSON tu khoi markdown hoac van ban tho.

    Args:
        text: Chuoi van ban tra ve tu mo hinh ngon ngu.

    Returns:
        Chuoi con JSON da lam sach de tien hanh giai ma cu phap.
    """
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    return cleaned


def validate_structured_output(raw_output: str) -> StructuredAnalysis | None:
    """Xac thuc chuoi phan hoi tho theo hop dong du lieu JSON dinh san.

    Args:
        raw_output: Chuoi phan hoi tu mo hinh ngon ngu.

    Returns:
        Doi tuong StructuredAnalysis da xac thuc thanh cong, hoac None neu vi pham.
    """
    json_str = extract_json_block(raw_output)
    try:
        data: dict[str, Any] = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    summary = data.get("summary")
    sentiment = data.get("sentiment")
    materiality = data.get("materiality_score")
    key_points = data.get("key_points")

    if not isinstance(summary, str) or not summary.strip():
        return None

    if sentiment not in ("pos", "neg", "neu"):
        return None

    if not isinstance(materiality, (int, float)) or not (0.0 <= float(materiality) <= 1.0):
        return None

    if not isinstance(key_points, list) or len(key_points) == 0:
        return None

    if not all(isinstance(k, str) and k.strip() for k in key_points):
        return None

    if HAS_PYDANTIC:
        try:
            return StructuredAnalysis.model_validate(data)
        except ValidationError:
            return None

    return StructuredAnalysis(
        summary=summary.strip(),
        sentiment=sentiment,
        materiality_score=float(materiality),
        key_points=[k.strip() for k in key_points],
    )
