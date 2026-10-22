"""Manage the entity catalog and map it to user watchlists."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

import yaml

from loguru import logger as _LOG

from src.core import paths
from src.core.user_manifest import load_user_manifest
from src.core.paths import PROJECT_ROOT

ENTITIES_JSON = paths.entities_dir() / "entities.json"
USERS_DIR = PROJECT_ROOT / "config" / "entities" / "users"
CONTEXT_GUARDS_YAML = PROJECT_ROOT / "config" / "entities" / "aliases" / "_context_guards.yaml"

# 3-character codes easily confused with abbreviations in financial news: never auto-matched by code.
CODE_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "ETF", "IPO", "ROE", "ROA", "EPS", "OTC", "GMT",
})

# Aliases that are too generic: place names, legal suffixes and generic trade descriptions.
# They leak into company aliases through the legal name: `CTCP Chứng khoán Guotai Haitong
# (Việt Nam)` produces the alias `Việt Nam`, so TICKER:IVS matched 164 articles and became
# the wrong top-1 ticker of the whole system.
# Matching uses the folded form (_fold: lowercase, no diacritics). Applies ONLY to
# securities (TICKER/ETF/SECURITY_OTHER); industry, country and theme groups take aliases
# from config/entities/aliases/*.yaml written by editors, where `xây dựng` and
# `công nghiệp` are valid aliases of that industry group.
GENERIC_ALIAS_STOPLIST = frozenset({
    # countries and administrative place names
    "viet nam", "vietnam", "ha noi", "tp ha noi", "ho chi minh", "tp ho chi minh",
    "thanh pho ho chi minh", "tphcm", "tp hcm", "sai gon", "da nang", "hai phong",
    "can tho", "song da", "mien bac", "mien nam", "mien trung",
    # exchanges: already separate EXCHANGE entities, must not be assigned to a ticker
    "hose", "hsx", "hnx", "upcom",
    # legal suffixes and generic trade descriptions
    "tap doan", "tong cong ty", "cong ty", "co phan", "dau tu", "dau tu va phat trien",
    "phat trien", "thuong mai", "thuong mai va dich vu", "dich vu", "xuat nhap khau",
    "xay dung", "xay lap", "san xuat", "cong nghiep", "nong nghiep", "quoc te", "viet",
    # short names that equal a dictionary word or common proper noun: `Trang` (CTCP Trang,
    # code TFC) also folds `trạng`, `trăng`, `trắng` (`tình trạng`, `mặt trăng`, `màu trắng`) and
    # the spelling `trang` in `trang sức`, `Nha Trang`, `thời trang`. Measured on 1,787 real
    # titles: 21 of 21 matches were wrong (0% correct) and TFC is too small to offset them.
    "trang",
})

# Security groups: aliases are generated from the legal name, so they pass through GENERIC_ALIAS_STOPLIST.
SECURITY_TYPES = ("TICKER", "ETF", "SECURITY_OTHER")

# Important short words (2-3 characters) protected from the length filter.
PROTECTED_SHORT_WORDS = frozenset({
    "quy", "my", "us", "eu", "fed", "vang", "dau", "cpi", "gdp",
    "fomc", "sbv", "ecb", "boj", "omo", "noxh", "hrc", "ctck", "tctd", "bds",
})

_CODE_RE = re.compile(r"\b[A-Z0-9]{3}\b")
# Official disclosure news (CBTT): `VND: Báo cáo tình hình quản trị...`.
# Exempts the code from CODE_STOPLIST when it starts the string and is followed by a colon.
_DISCLOSURE_PREFIX_RE = re.compile(r"^([A-Z0-9]{3})\s*:")
# Left context that makes a 3-character code not a ticker: `TP.HCM`, `UBND HCM`, `PGD Tân Bình`.
_CODE_LEFT_BLOCK_RE = re.compile(r"(?:\bT\.?P\.?\s*|\bUBND\s*|\bkhu\s+vực\s*)$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

# Group in the subscription file -> order of types tried when mapping a code to an entity_id.
_CATEGORY_TYPES = {
    "tickers": ("TICKER", "SECURITY_OTHER", "ETF"),
    "stocks": ("TICKER", "SECURITY_OTHER", "ETF"),
    "etfs": ("ETF", "SECURITY_OTHER"),
    "indices": ("INDEX",),
    "exchanges": ("EXCHANGE",),
    "nations": ("MACRO_GEO",),
    "themes": ("MACRO_THEME",),
    "macro": ("MACRO_GEO", "MACRO_THEME"),
    "assets": ("ASSET_CLASS",),
    "institutions": ("INSTITUTION",),
}
_INDUSTRY_TYPES = ("INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3")



def _fold(s: str) -> str:
    """Convert a string to lowercase without diacritics for matching.

    Args:
        s: Original text.

    Returns:
        Lowercase text with Vietnamese diacritics removed.
    """
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _WS_RE.sub(" ", s.lower()).strip()


def _locate_folded(key: str, raw: str) -> tuple[str | None, tuple[int, int] | None]:
    """Find the original substring that corresponds to a folded key.

    Args:
        key: Folded key without diacritics.
        raw: Original text to search.

    Returns:
        Tuple of the substring found and its (start, end) span; (None, None) when not found.
    """
    n = len(key)
    for m in re.finditer(r"\S+", raw):
        start = m.start()
        # raw can be longer than key (diacritics split out under NFD, whitespace collapses)
        for end in range(start + n, min(len(raw), start + n + 16) + 1):
            if _fold(raw[start:end]) == key:
                return raw[start:end], (start, end)
    return None, None


def _load_context_guards() -> tuple[dict[str, list[str]], set[str]]:
    """Load the context guards that block noisy entity matches.

    Returns:
        Tuple of the blocking phrases per entity_id and the set of entity_ids whose single-word aliases are dropped.
    """
    if not CONTEXT_GUARDS_YAML.exists():
        return {}, set()
    raw = yaml.safe_load(CONTEXT_GUARDS_YAML.read_text(encoding="utf-8")) or {}
    blocks: dict[str, list[str]] = {}
    drop_bare: set[str] = set()
    for eid, cfg in (raw or {}).items():
        cfg = cfg or {}
        folded = [f for f in (_fold(p) for p in (cfg.get("block_in") or [])) if f]
        if folded:
            blocks[str(eid)] = folded
        if cfg.get("drop_bare"):
            drop_bare.add(str(eid))
    return blocks, drop_bare


class EntityRegistry:
    """Entity registry that supports recognition and links to subscribing users.

    Attributes:
        entities: Entities keyed by entity_id.
        subscriptions: Mapping from user name to the set of watched entity_ids.
        aliases_dropped: Number of aliases dropped for being too generic.
    """

    def __init__(self, entities: list[dict], subscriptions: dict | None = None):
        """Initialize the EntityRegistry.

        Args:
            entities: Entity dicts.
            subscriptions: Optional per-user subscription mapping.
        """
        self.entities = {e["entity_id"]: e for e in entities}
        # Alias index (folded) -> list[entity_id]; only aliases that are long enough or in the short-word whitelist.
        self._alias_index: dict[str, list[str]] = {}
        # Original form of each alias under the same folded key, used to confirm a match
        # (see _alias_match): blocks false positives from diacritic or case folding and
        # returns the verbatim surface.
        self._alias_forms: dict[str, list[str]] = {}
        # Look up GICS industries by CODE (normalized like the other code groups, not by name).
        self._industry_ids_by_code: dict[str, list[str]] = {}
        # Number of aliases dropped as too generic, so build/check scripts can report it instead of staying silent.
        self.aliases_dropped = 0
        # Block single-word aliases that are ambiguous by context (config/entities/aliases/_context_guards.yaml).
        self._context_guards, self._drop_bare_alias = _load_context_guards()
        for eid, e in self.entities.items():
            is_security = e["type"] in SECURITY_TYPES
            # Aliases generated from the legal name of a security can be place names or
            # generic suffixes (`viet nam` -> TICKER:IVS, `song da` -> TICKER:SJG) and would
            # match almost every article. They are removed in the registry (not only in the
            # index) so every consumer of e["aliases"] (_passes_noise_filter,
            # _silver_noise_signals) sees the cleaned alias set. The entities.json file on
            # disk stays unchanged for audit; build_entities.py filters on the next build.
            # This is the runtime source of truth.
            if is_security:
                kept = [a for a in e.get("aliases", []) if _fold(a) not in GENERIC_ALIAS_STOPLIST]
                if len(kept) != len(e.get("aliases", [])):
                    self.aliases_dropped += len(e["aliases"]) - len(kept)
                    e["aliases"] = kept
            for a in e.get("aliases", []):
                key = _fold(a)
                # drop_bare: an industry name that is a single word equal to a common word
                # (`Nước`, `Điện`, `Giấy`, `Quỹ`). Drop the single-word alias and keep only
                # the phrases that carry the intent in industries.yaml. This is an allow
                # list and never acts as a blocklist. See _context_guards.yaml.
                if eid in self._drop_bare_alias and " " not in key:
                    self.aliases_dropped += 1
                    continue
                # Length threshold: securities keep aliases of >= 4 characters (a generated
                # 3-character alias is only a short name that duplicates the match by CODE,
                # adds no value and adds noise). The other groups take aliases from
                # config/entities/aliases/*.yaml written by editors, so >= 3 is allowed; this
                # restores real aliases that were wrongly lost: HNX, HSX, USA, DXY, FDI, IMF,
                # SSC, Nga, ECB, BOJ.
                if len(key) >= 4 or key in PROTECTED_SHORT_WORDS or (not is_security and len(key) >= 3):
                    self._alias_index.setdefault(key, []).append(eid)
                    self._alias_forms.setdefault(key, []).append(a)
            if e["type"] in _INDUSTRY_TYPES:
                self._industry_ids_by_code.setdefault(e["code"], []).append(eid)

        # subscriptions: {user name -> set of resolved entity_ids}
        self.subscriptions: dict[str, set[str]] = {
            name: {i for i in ids if i in self.entities}
            for name, ids in (subscriptions or {}).items()
        }

    # ---- lookup ----------------------------------------------------------
    def get(self, entity_id: str) -> dict | None:
        """Return the details of one entity by ID.

        Args:
            entity_id: Entity identifier.

        Returns:
            Entity info dict, or None if not found.
        """
        return self.entities.get(entity_id)

    def by_type(self, *types: str) -> list[dict]:
        """Filter entities by one or more types.

        Args:
            *types: Entity type strings to filter by.

        Returns:
            Entity dicts that match.
        """
        ts = set(types)
        return [e for e in self.entities.values() if e["type"] in ts]

    # ---- per-user subscriptions ----------------------------------------
    def select(self, doc: dict) -> tuple[set[str], list[tuple[str, str]]]:
        """Resolve a user watchlist config to a set of entity IDs.

        Args:
            doc: User config data loaded from the YAML file.

        Returns:
            Tuple of the valid entity_ids and the list of unknown codes.
        """
        ids: set[str] = set()
        unknown: list[tuple[str, str]] = []
        doc = doc or {}

        for cat, types in _CATEGORY_TYPES.items():
            for code in doc.get(cat) or []:
                c_clean = str(code).strip().upper()
                hit = next((f"{t}:{c_clean}" for t in types if f"{t}:{c_clean}" in self.entities), None)
                ids.add(hit) if hit else unknown.append((cat, str(code)))

        # industries: by industry CODE only (for example THEP, NGAN_HANG, QUY)
        for val in doc.get("industries") or []:
            hits = self._industry_ids_by_code.get(str(val).strip().upper())
            ids.update(hits) if hits else unknown.append(("industries", str(val)))

        for eid in doc.get("entities") or []:   # escape hatch: verbatim entity_id
            ids.add(eid) if eid in self.entities else unknown.append(("entities", str(eid)))

        return ids, unknown

    def resolve_subscription(self, name: str) -> set[str]:
        """Return the entity IDs a user subscribes to.

        Args:
            name: User identifier.

        Returns:
            Entity_ids the user subscribed to.
        """
        return set(self.subscriptions.get(name, set()))

    def subscribers_for(self, entity_ids) -> set[str]:
        """Find the users subscribed to the given entities.

        Args:
            entity_ids: Entity_ids to look up.

        Returns:
            Names of users whose subscription contains at least one of the entities.
        """
        ids = set(entity_ids)
        return {u for u, subs in self.subscriptions.items() if subs & ids}

    # ---- detect (detailed matcher that records whether a match came from code or alias) ----
    def detect(self, text: str) -> list[dict]:
        """Detect the entities that appear in a text, with the match source.

        Args:
            text: Text in which to detect entities.

        Returns:
            Detected entity dicts with the surface form and the match basis.
        """
        if not text:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for m in _CODE_RE.finditer(text):
            code = m.group()
            # Exempt official CBTT disclosures at the start of a title (for example `VND: Báo cáo quản trị...`).
            is_disclosure_prefix = (m.start() == 0 and _DISCLOSURE_PREFIX_RE.match(text))
            if code in CODE_STOPLIST and not is_disclosure_prefix:
                continue
            if _CODE_LEFT_BLOCK_RE.search(text[:m.start()]):
                continue                       # `TP.HCM` and `UBND HCM` are not the HCM ticker
            # PGD guard: the PGD ticker (Khí thấp áp) is confused with the bank branch `Phòng giao dịch`.
            if code == "PGD":
                left_text = text[:m.start()]
                right_text = text[m.end():]
                is_bank_pgd = (
                    re.search(r"(?:thành\s+lập|đổi\s+tên|chi\s+nhánh|điểm|quản\s+lý|tên|[/\\])\s*$", left_text, re.IGNORECASE)
                    or re.match(r"^\s+[A-ZÀ-Ỹ0-9]", right_text)  # `PGD Chợ Tân Bình`, `PGD Quận 9`
                    or any(b in text for b in ("MBB:", "TCB:", "VCB:", "BID:", "CTG:", "ACB:", "HDB:", "SHB:", "VPB:", "STB:", "TPB:", "LPB:", "MSB:", "VIB:", "OCB:", "EIB:"))
                )
                if is_bank_pgd:
                    continue

            # EXCHANGE is in the list so a code such as HNX in a title resolves to EXCHANGE:*
            for etype in ("TICKER", "ETF", "SECURITY_OTHER", "INDEX", "EXCHANGE",
                          "MACRO_GEO", "MACRO_THEME", "ASSET_CLASS", "INSTITUTION"):
                eid = f"{etype}:{code}"
                if eid in self.entities and eid not in seen:
                    ent_tier = self.entities[eid].get("attributes", {}).get("tier", 1)
                    if etype == "TICKER" and ent_tier == 2 and not is_disclosure_prefix:
                        continue
                    seen.add(eid)
                    out.append({"entity_id": eid, "via": "code", "surface": code})
                    break

        cand: list[tuple[tuple[int, int] | None, str | None, list[str], str]] = []
        folded = _fold(text)
        for key, eids in self._alias_index.items():
            # Prefilter with `in` before running the regex: the index has about 4.3k aliases and
            # most do not appear in a title. A substring test is about 100 times cheaper than the
            # regex and does not change semantics (the word-boundary regex stays the deciding
            # condition).
            if key not in folded:
                continue
            if not re.search(r"\b" + re.escape(key) + r"\b", folded):
                continue
            ok, surface, span = self._alias_match(key, text)
            if not ok:
                continue
            cand.append((span, surface, eids, key))

        # Remove overlap BETWEEN SECURITIES: one company name cannot sit inside another
        # company name. `Tập đoàn Xăng dầu Việt Nam` (PLX) contains `dầu Việt Nam` (OIL), so
        # only the longer match is kept. Not applied to industries or macro entities:
        # `Ngân hàng` inside the TCB name is a correct match and both must be kept.
        cand.sort(key=lambda c: -((c[0][1] - c[0][0]) if c[0] else 0))
        taken: list[tuple[int, int]] = []
        for span, surface, eids, key in cand:
            sec = [e for e in eids if self.entities[e]["type"] in SECURITY_TYPES]
            if span and sec and any(t[0] <= span[0] and span[1] <= t[1] for t in taken):
                eids = [e for e in eids if e not in sec]
                if not eids:
                    continue
            if span and sec:
                taken.append(span)
            for eid in eids:
                if self._blocked_by_context(eid, key, folded):
                    continue
                if self._blocked_by_morphology(eid, key, surface, span, text):
                    continue
                if eid not in seen:
                    seen.add(eid)
                    out.append({"entity_id": eid, "via": "alias", "surface": surface})

        result = []
        for o in out:
            e = self.entities[o["entity_id"]]
            result.append({
                "entity_id": e["entity_id"], "type": e["type"], "code": e["code"],
                "canonical_name": e["canonical_name"], "via": o["via"],
                "surface": o["surface"],
            })
        return result

    def _blocked_by_context(self, eid: str, key: str, folded: str) -> bool:
        """Check whether the alias occurrence is fully covered by blocking contexts.

        Args:
            eid: Entity identifier.
            key: Folded alias key.
            folded: Folded title string.

        Returns:
            True if the alias occurs only inside blocked contexts, otherwise False.
        """
        phrases = self._context_guards.get(eid)
        if not phrases:
            return False
        stripped = folded
        for ph in phrases:
            if key in ph:
                # Word boundaries are required: a plain str.replace would also remove `nuoc ta`
                # inside `nuoc tang gia` and lose a correct match.
                stripped = re.sub(r"\b" + re.escape(ph) + r"\b", " ", stripped)
        return not re.search(r"\b" + re.escape(key) + r"\b", stripped)

    _INTL_AFTER_MY = frozenset({
        "trump", "biden", "obama", "bush", "clinton", "harris", "hegseth",
        "powell", "yellen", "blinken", "fed", "sec", "cpi", "ppi", "pmi", "gdp",
        "wall", "street", "nasdaq", "dow", "jones", "sp500", "s&p", "pentagon",
        "donald", "joe", "kamala", "barack", "george", "bill", "ronald",
    })
    _VIETNAMESE_PREFIXES = frozenset({"á", "phú", "phù", "nam", "bắc"})
    _HONORIFIC_PREFIXES = frozenset({"bà", "ông", "cô", "chị", "anh", "em", "thị", "văn"})

    def _blocked_by_morphology(self, eid: str, key: str, surface: str | None,
                               span: tuple[int, int] | None, raw: str) -> bool:
        """Block false matches caused by compound-word or proper-noun morphology.

        Args:
            eid: Entity identifier.
            key: Folded alias key.
            surface: Matched surface string.
            span: (start, end) position of the match in the original text.
            raw: Original text.

        Returns:
            True if the match violates a morphology rule, otherwise False.
        """
        if not span or not raw:
            return False
        if eid == "MACRO_GEO:MY" and key == "my":
            start, end = span
            # 1. Capitalized suffix: the word after `Mỹ` is a capitalized Vietnamese word (Mỹ Thuận, Mỹ Tho, Mỹ Đình, Mỹ Thủy).
            after = raw[end:].lstrip()
            m_after = re.match(r"^([A-ZÀ-Ỹa-zà-ỹ0-9]+)", after)
            if m_after:
                next_w = m_after.group(1)
                if next_w[0].isupper() and next_w.lower() not in self._INTL_AFTER_MY:
                    return True
            # 2. Prefix guard: `Mỹ` follows a compound proper name (Á Mỹ, Phú Mỹ) or an honorific/personal name (Bà Phạm Thị Mỹ Diệu).
            before = raw[:start].rstrip()
            m_before = re.search(r"([A-ZÀ-Ỹa-zà-ỹ0-9]+)$", before)
            if m_before:
                prev_w = m_before.group(1).lower()
                if prev_w in self._VIETNAMESE_PREFIXES or prev_w in self._HONORIFIC_PREFIXES:
                    return True

        if eid == "MACRO_GEO:NGA" and key == "nga":
            start, end = span
            # 1. Prefix guard: block a personal name when `Nga` follows an honorific (Bà, Ông, Chị, Cô) or a given name (Kim Nga, Thúy Nga, Thiên Nga).
            before = raw[:start].rstrip()
            m_before = re.search(r"([A-ZÀ-Ỹa-zà-ỹ0-9]+)$", before)
            if m_before:
                prev_w = m_before.group(1).lower()
                if prev_w in self._HONORIFIC_PREFIXES or prev_w in {"kim", "thúy", "thuy", "thiên", "thien", "bích", "bich", "hoàng", "hoang"}:
                    return True
            # 2. Suffix guard: block online account names and compound foreign names (`Nga Rose`, `Nga Phạm`).
            after = raw[end:].lstrip()
            m_after = re.match(r"^([A-ZÀ-Ỹa-zà-ỹ0-9]+)", after)
            if m_after:
                next_w = m_after.group(1)
                # The next word is a personal-name token rather than a word from diplomatic or economic usage.
                if next_w.lower() in {"rose", "pham", "nguyen", "tran", "le"} or (next_w[0].isupper() and next_w.lower() in {"hoang", "mai", "lan"}):
                    return True
        return False


    def _alias_match(self, key: str, raw: str) -> tuple[bool, str | None, tuple[int, int] | None]:
        """Confirm an alias match and extract the verbatim surface string.

        Args:
            key: Folded alias key.
            raw: Original text.

        Returns:
            Tuple of the match flag, the surface string and the (start, end) span.
        """
        forms = self._alias_forms.get(key) or []
        for f in forms:
            #  * Alias WITH diacritics: require the accented form, case-insensitive. Industry
            #    names in industries.yaml that start with a capital (`Điện`, `Nước`) are still
            #    common nouns; requiring the capital would wrongly block `giá điện` and `ngành điện`.
            #  * SHORT uppercase ASCII symbols (<=3: US, EU, DXY): case must match, otherwise
            #    `thẩm mỹ` would match MACRO_GEO:MY. Long symbols (HOSE, UPCOM) are not
            #    ambiguous with common words, so case is ignored; the press often writes `HoSE`.
            flags = 0 if (f.isascii() and f.isupper() and len(f) <= 3) else re.IGNORECASE
            m = re.search(r"\b" + re.escape(f) + r"\b", raw, flags)
            if m:
                return True, m.group(0), m.span()
        if " " not in key:
            return False, None, None
        surface, span = _locate_folded(key, raw)
        return True, surface, span

    # ---- text matching (backward compatible) -------------------------------
    def match(self, text: str) -> list[dict]:
        """Return the unique entities that appear in a text.

        Args:
            text: Text to analyze.

        Returns:
            Matching entity dicts.
        """
        return [self.entities[d["entity_id"]] for d in self.detect(text)]


def _load_manifest() -> dict:
    """Load the user switches from `<root>/subscriptions/manifest.yaml` (ADR-0026.D5).

    Returns:
        Manifest dict.
    """
    return load_user_manifest()


def _user_enabled(manifest: dict, stem: str) -> bool:
    """Check whether a user is enabled to receive news in the manifest.

    Args:
        manifest: Manifest config dict.
        stem: User identifier.

    Returns:
        True if the user is enabled, otherwise False.
    """
    if not manifest.get("enabled", True):
        return False
    return bool(manifest.get("users", {}).get(stem, manifest.get("default", True)))


def _load_subscriptions(reg: EntityRegistry) -> tuple[dict, dict]:
    """Read and resolve the user watchlist config files.

    Args:
        reg: EntityRegistry used to resolve entities.

    Returns:
        Tuple of the watchlist dict and the per-user dict of unknown-code warnings.
    """
    subs: dict[str, set[str]] = {}
    warnings: dict[str, list] = {}
    if not USERS_DIR.exists():
        return subs, warnings
    manifest = _load_manifest()
    for f in sorted(USERS_DIR.glob("*.yaml")):
        if not _user_enabled(manifest, f.stem):
            # `default: false` silently disables a user who has a subscription file but is not
            # listed in the manifest. A warning is logged so this does not go unnoticed.
            _LOG.warning(
                "[entities] users/{}.yaml co ton tai nhung KHONG duoc bat trong {} "
                "(default={}) -> nguoi dung nay se khong nhan duoc bai nao.",
                f.stem, "subscriptions/manifest.yaml", manifest.get("default", True))
            continue                               # the user is switched off in the manifest: skip
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        ids, unknown = reg.select(doc)
        subs[f.stem] = ids
        if unknown:
            warnings[f.stem] = unknown
    return subs, warnings


@lru_cache(maxsize=1)
def load_registry() -> EntityRegistry:
    """Load and build the shared EntityRegistry instance from the standard data file.

    Returns:
        Cached EntityRegistry with subscriptions and subscription warnings attached.
    """
    entities = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))["entities"]
    reg = EntityRegistry(entities)                 # build the index first
    subs, warnings = _load_subscriptions(reg)      # then resolve user subscriptions (manifest-filtered)
    reg.subscriptions = subs
    reg.subscription_warnings = warnings
    return reg
