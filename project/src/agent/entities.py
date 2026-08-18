"""
entities.py — Registry thực thể + đăng ký theo NGƯỜI DÙNG.

Load danh sách thực thể (data/entities/entities.json) và các file đăng ký của người
dùng (config/entities/users/<name>.yaml — mỗi file liệt kê entity theo từng nhóm), cho phép:

  * registry.get(entity_id)                 -> 1 thực thể
  * registry.detect(title)                  -> list thực thể nhận diện trong text (L1)
  * registry.subscribers_for(entity_ids)    -> set người dùng có đăng ký chạm tới
  * registry.resolve_subscription("AnPT")   -> set entity_id người dùng đăng ký

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
USERS_DIR = PROJECT_ROOT / "config" / "entities" / "users"
MANIFEST_YAML = PROJECT_ROOT / "config" / "entities" / "manifest.yaml"

# Mã 3 ký tự dễ nhầm với từ viết tắt trong tin tài chính -> không auto-match by code.
CODE_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "ETF", "IPO", "ROE", "ROA", "EPS", "OTC", "GMT",
})

_CODE_RE = re.compile(r"\b[A-Z0-9]{3}\b")
_WS_RE = re.compile(r"\s+")

# Nhóm trong file đăng ký -> thứ tự type thử khi ánh xạ code sang entity_id.
_CATEGORY_TYPES = {
    "tickers": ("TICKER", "SECURITY_OTHER", "ETF"),
    "stocks": ("TICKER", "SECURITY_OTHER", "ETF"),
    "etfs": ("ETF", "SECURITY_OTHER"),
    "indices": ("INDEX",),
    "exchanges": ("EXCHANGE",),
}
_INDUSTRY_TYPES = ("INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3")


def _fold(s: str) -> str:
    """lower + bỏ dấu tiếng Việt để so khớp alias/tên ổn định."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _WS_RE.sub(" ", s.lower()).strip()


class EntityRegistry:
    def __init__(self, entities: list[dict], subscriptions: dict | None = None):
        self.entities = {e["entity_id"]: e for e in entities}
        # index alias (đã fold) -> entity_id, chỉ alias đủ dài để giảm nhiễu
        self._alias_index: dict[str, str] = {}
        # tra ngành GICS theo CODE (chuẩn hoá đồng bộ với các nhóm code khác — KHÔNG theo tên)
        self._industry_ids_by_code: dict[str, list[str]] = {}
        for eid, e in self.entities.items():
            for a in e.get("aliases", []):
                key = _fold(a)
                if len(key) >= 4:
                    self._alias_index.setdefault(key, eid)
            if e["type"] in _INDUSTRY_TYPES:
                self._industry_ids_by_code.setdefault(e["code"], []).append(eid)

        # subscriptions: {tên người dùng -> set(entity_id đã giải)}
        self.subscriptions: dict[str, set[str]] = {
            name: {i for i in ids if i in self.entities}
            for name, ids in (subscriptions or {}).items()
        }

    # ---- lookup ----------------------------------------------------------
    def get(self, entity_id: str) -> dict | None:
        return self.entities.get(entity_id)

    def by_type(self, *types: str) -> list[dict]:
        ts = set(types)
        return [e for e in self.entities.values() if e["type"] in ts]

    # ---- đăng ký theo người dùng ----------------------------------------
    def select(self, doc: dict) -> tuple[set[str], list[tuple[str, str]]]:
        """Ánh xạ 1 file đăng ký (liệt kê theo nhóm) → (set entity_id, unknown[])."""
        ids: set[str] = set()
        unknown: list[tuple[str, str]] = []
        doc = doc or {}

        for cat, types in _CATEGORY_TYPES.items():
            for code in doc.get(cat) or []:
                hit = next((f"{t}:{code}" for t in types if f"{t}:{code}" in self.entities), None)
                ids.add(hit) if hit else unknown.append((cat, str(code)))

        # industries: chỉ theo CODE ngành (vd THEP, NGAN_HANG) — đồng bộ với các nhóm code khác,
        # KHÔNG khớp theo tên. Viết hoa để so khớp không phân biệt hoa/thường (code trong data in hoa).
        for val in doc.get("industries") or []:
            hits = self._industry_ids_by_code.get(str(val).strip().upper())
            ids.update(hits) if hits else unknown.append(("industries", str(val)))

        for eid in doc.get("entities") or []:   # cửa thoát: entity_id nguyên bản
            ids.add(eid) if eid in self.entities else unknown.append(("entities", str(eid)))

        return ids, unknown

    def resolve_subscription(self, name: str) -> set[str]:
        return set(self.subscriptions.get(name, set()))

    def subscribers_for(self, entity_ids) -> set[str]:
        """Người dùng có đăng ký chạm tới tập entity này (giao ≠ ∅)."""
        ids = set(entity_ids)
        return {u for u, subs in self.subscriptions.items() if subs & ids}

    # ---- detect (matcher chi tiết, ghi rõ khớp qua code/alias) ------------
    def detect(self, text: str) -> list[dict]:
        """Trả list thực thể nhận diện, kèm `via` ('code'|'alias'). Dùng cho L1."""
        if not text:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for m in _CODE_RE.findall(text):
            if m in CODE_STOPLIST:
                continue
            for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX"):
                eid = f"{etype}:{m}"
                if eid in self.entities and eid not in seen:
                    seen.add(eid); out.append({"entity_id": eid, "via": "code"})
                    break
        folded = _fold(text)
        for key, eid in self._alias_index.items():
            if eid in seen:
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

    # ---- text matching (tương thích ngược) -------------------------------
    def match(self, text: str) -> list[dict]:
        """Trả list thực thể (unique, theo thứ tự xuất hiện) nhận diện trong text."""
        return [self.entities[d["entity_id"]] for d in self.detect(text)]


def _load_manifest() -> dict:
    """Công tắc DEV (config/entities/manifest.yaml). Thiếu file → bật tất (tương thích cũ)."""
    if not MANIFEST_YAML.exists():
        return {"enabled": True, "default": True, "users": {}}
    m = yaml.safe_load(MANIFEST_YAML.read_text(encoding="utf-8")) or {}
    return {
        "enabled": bool(m.get("enabled", True)),
        "default": bool(m.get("default", True)),
        "users": m.get("users") or {},
    }


def _user_enabled(manifest: dict, stem: str) -> bool:
    """Người dùng có được DEV bật không (manifest.users[stem], fallback manifest.default)."""
    if not manifest.get("enabled", True):
        return False
    return bool(manifest.get("users", {}).get(stem, manifest.get("default", True)))


def _load_subscriptions(reg: EntityRegistry) -> tuple[dict, dict]:
    """Đọc users/*.yaml ĐƯỢC DEV BẬT (manifest.yaml) → ({tên: set ids}, {tên: unknown[]})."""
    subs: dict[str, set[str]] = {}
    warnings: dict[str, list] = {}
    if not USERS_DIR.exists():
        return subs, warnings
    manifest = _load_manifest()
    for f in sorted(USERS_DIR.glob("*.yaml")):
        if not _user_enabled(manifest, f.stem):
            continue                               # DEV tắt user này → bỏ qua
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        ids, unknown = reg.select(doc)
        subs[f.stem] = ids
        if unknown:
            warnings[f.stem] = unknown
    return subs, warnings


@lru_cache(maxsize=1)
def load_registry() -> EntityRegistry:
    entities = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))["entities"]
    reg = EntityRegistry(entities)                 # dựng index trước
    subs, warnings = _load_subscriptions(reg)      # rồi giải đăng ký người dùng (đã lọc manifest)
    reg.subscriptions = subs
    reg.subscription_warnings = warnings
    return reg
