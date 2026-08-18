"""
entities.py — Registry thực thể + resolver nhóm cho lớp L3 agent.

Load danh sách thực thể (data/entities/entities.json) và cấu hình nhóm
(config/entities/entity_groups.yaml), cho phép:

  * registry.get(entity_id)              -> 1 thực thể
  * registry.resolve_group("fta")        -> set entity_id thuộc nhóm
  * registry.match(text, group="co_ban") -> list thực thể nhận diện trong text

Nhận diện trong text:
  - TICKER/ETF/INDEX: khớp CODE theo ranh giới từ (in hoa), trừ stoplist mơ hồ.
  - Mọi thực thể có alias: khớp alias (không phân biệt hoa/thường & dấu).

Registry sinh bởi scripts/build_entities.py — chạy lại khi dữ liệu gốc đổi.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTITIES_JSON = PROJECT_ROOT / "data" / "entities" / "entities.json"
GROUPS_YAML = PROJECT_ROOT / "config" / "entities" / "entity_groups.yaml"

# Mã 3 ký tự dễ nhầm với từ viết tắt trong tin tài chính -> không auto-match by code.
CODE_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "ETF", "IPO", "ROE", "ROA", "EPS", "OTC", "GMT",
})

_CODE_RE = re.compile(r"\b[A-Z0-9]{3}\b")
_WS_RE = re.compile(r"\s+")


def _fold(s: str) -> str:
    """lower + bỏ dấu tiếng Việt để so khớp alias ổn định."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _WS_RE.sub(" ", s.lower()).strip()


class EntityRegistry:
    def __init__(self, entities: list[dict], groups: dict):
        self.entities = {e["entity_id"]: e for e in entities}
        self.groups = groups or {}
        # index alias (đã fold) -> entity_id, chỉ alias đủ dài để giảm nhiễu
        self._alias_index: dict[str, str] = {}
        for eid, e in self.entities.items():
            for a in e.get("aliases", []):
                key = _fold(a)
                if len(key) >= 4:
                    self._alias_index.setdefault(key, eid)
        # precompute tập entity của mỗi nhóm (để map entity -> group nhanh)
        self._resolved_groups: dict[str, set[str]] = {
            g: self.resolve_group(g) for g in self.groups
        }

    # ---- lookup ----------------------------------------------------------
    def get(self, entity_id: str) -> dict | None:
        return self.entities.get(entity_id)

    def by_type(self, *types: str) -> list[dict]:
        ts = set(types)
        return [e for e in self.entities.values() if e["type"] in ts]

    # ---- group resolution ------------------------------------------------
    def resolve_group(self, name: str) -> set[str]:
        cfg = self.groups.get(name)
        if cfg is None:
            raise KeyError(f"Nhóm không tồn tại: {name}")
        selected: set[str] = set()
        types = set(cfg.get("include_types") or [])
        if types:
            selected |= {eid for eid, e in self.entities.items() if e["type"] in types}
        for g1 in cfg.get("include_gics1") or []:
            selected |= {
                eid for eid, e in self.entities.items()
                if e["type"] == "TICKER" and e["attributes"].get("gics1") == g1
            }
        sectors = set(cfg.get("include_sectors") or [])
        if sectors:
            selected |= {
                eid for eid, e in self.entities.items()
                if e["type"] == "SECTOR_FPA" and e["code"] in sectors
            }
        selected |= set(cfg.get("include_entities") or [])
        selected -= set(cfg.get("exclude_entities") or [])
        # chỉ giữ id hợp lệ
        return {eid for eid in selected if eid in self.entities}

    def groups_for(self, entity_ids) -> set[str]:
        """Các nhóm (đăng ký) mà tập entity này chạm tới (giao ≠ ∅)."""
        ids = set(entity_ids)
        return {g for g, members in self._resolved_groups.items() if members & ids}

    # ---- detect (matcher chi tiết, ghi rõ khớp qua code/alias) ------------
    def detect(self, text: str, group: str | None = None) -> list[dict]:
        """Như match() nhưng trả kèm `via` ('code'|'alias'). Dùng cho L1."""
        if not text:
            return []
        allowed = self.resolve_group(group) if group else None
        out: list[dict] = []
        seen: set[str] = set()
        for m in _CODE_RE.findall(text):
            if m in CODE_STOPLIST:
                continue
            for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX"):
                eid = f"{etype}:{m}"
                if eid in self.entities and eid not in seen:
                    if allowed is None or eid in allowed:
                        seen.add(eid); out.append({"entity_id": eid, "via": "code"})
                    break
        folded = _fold(text)
        for key, eid in self._alias_index.items():
            if eid in seen:
                continue
            if allowed is not None and eid not in allowed:
                continue
            if re.search(r"\b" + re.escape(key) + r"\b", folded):
                seen.add(eid); out.append({"entity_id": eid, "via": "alias"})
        result = []
        for o in out:
            e = self.entities[o["entity_id"]]
            result.append({
                "entity_id": e["entity_id"], "type": e["type"], "code": e["code"],
                "canonical_name": e["canonical_name"], "via": o["via"],
            })
        return result

    # ---- text matching ---------------------------------------------------
    def match(self, text: str, group: str | None = None) -> list[dict]:
        """Trả list thực thể (unique, theo thứ tự xuất hiện) nhận diện trong text.
        Nếu truyền `group`, chỉ giữ thực thể thuộc nhóm đó."""
        if not text:
            return []
        allowed = self.resolve_group(group) if group else None
        found: list[str] = []
        seen: set[str] = set()

        # 1) khớp CODE (in hoa, ranh giới từ)
        for m in _CODE_RE.findall(text):
            if m in CODE_STOPLIST:
                continue
            for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX"):
                eid = f"{etype}:{m}"
                if eid in self.entities and eid not in seen:
                    if allowed is None or eid in allowed:
                        seen.add(eid); found.append(eid)
                    break

        # 2) khớp ALIAS (fold, substring theo ranh giới từ)
        folded = _fold(text)
        for key, eid in self._alias_index.items():
            if eid in seen:
                continue
            if allowed is not None and eid not in allowed:
                continue
            if re.search(r"\b" + re.escape(key) + r"\b", folded):
                seen.add(eid); found.append(eid)

        return [self.entities[eid] for eid in found]


@lru_cache(maxsize=1)
def load_registry() -> EntityRegistry:
    entities = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))["entities"]
    groups = (yaml.safe_load(GROUPS_YAML.read_text(encoding="utf-8")) or {}).get("groups", {}) \
        if GROUPS_YAML.exists() else {}
    return EntityRegistry(entities, groups)
