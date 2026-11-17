"""Map entities named by the model to canonical catalog identifiers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.agent.entities import (
    CODE_STOPLIST,
    GENERIC_ALIAS_STOPLIST,
    EntityRegistry,
    _fold,
    _normalize_vn_tones,
)

# Business boundary: the model decides which entities an article contains; this module
# only looks up what the model named. It does not detect extra entities, infer, or
# overrule the model; an unresolved name is recorded as outside the catalog. Each group
# code has its own lookup: tickers need exact match with an abbreviation stoplist,
# company names need alias match with morphology guards, closed groups use direct tables.

# Group codes emitted by the model, mapped to the entity types allowed in the catalog lookup.
GROUP_TYPES: dict[str, tuple[str, ...]] = {
    "TIC": ("TICKER", "ETF", "SECURITY_OTHER"),
    "COM": ("TICKER", "UNLISTED_ORG"),
    "PER": (),                       # needs a leadership table, see the note below
    "FND": ("ETF", "SECURITY_OTHER"),
    "IDX": ("INDEX",),
    "EXC": ("EXCHANGE",),
    "IND": ("INDUSTRY_GICS3", "INDUSTRY_GICS2", "INDUSTRY_GICS1"),
    "GEO": ("MACRO_GEO",),
    "THM": ("MACRO_THEME",),
    "AST": ("ASSET_CLASS",),
    "INS": ("INSTITUTION",),
}

VALID_GROUPS = frozenset(GROUP_TYPES)

# Group `PER` has no lookup source: the leadership table that maps person names to
# company codes does not exist yet. Until it does, every person name falls outside the
# catalog by design. The value of this group in the first phase is data collection to
# build that table, so it is measured by the number of names collected, not by the
# lookup success rate.
GROUPS_WITHOUT_RESOLVER = frozenset({"PER"})

_CODE_RE = re.compile(r"^[A-Z0-9]{3}$")
_FUND_CODE_RE = re.compile(r"^[A-Z0-9]{6,10}$")
_DISCLOSURE_RE = re.compile(r"^([A-Z0-9]{3})\s*:")
_CORP_PREFIX_RE = re.compile(
    r"^(?:ctcp|cong ty co phan|cong ty tnhh mtv|cong ty tnhh|cong ty|"
    r"tap doan|tong cong ty|ngan hang tmcp|ngan hang thuong mai co phan|"
    r"ngan hang|ctck|cong ty chung khoan)\b[\s\-:]*",
)
_CORP_SUFFIX_RE = re.compile(r"[\s\-–]+(?:ctcp|jsc|ltd|plc|inc|corp)$")


def _strip_corporate_affixes(folded: str) -> str:
    """Strip common Vietnamese legal prefixes and suffixes from a folded organization name.

    Args:
        folded: Lowercase diacritic-stripped name.

    Returns:
        Normalized core brand string, or an empty string if stripped down to generic words.
    """
    s = folded.strip()
    for _ in range(3):
        nxt = _CORP_PREFIX_RE.sub("", s).strip()
        if nxt == s:
            break
        s = nxt
    s = _CORP_SUFFIX_RE.sub("", s).strip()
    if len(s) < 3 or s in GENERIC_ALIAS_STOPLIST:
        return ""
    return s


@dataclass
class ResolvedEntity:
    """Lookup result of one entity named by the model.

    Attributes:
        surface: Verbatim string named by the model.
        group: Group code assigned by the model.
        entity_id: Canonical identifier, or None when not found.
        type: Entity type, or None when not found.
        method: Lookup method (`semantic`, `alias` or `exact_code`).
        in_list: True when the entity exists in the catalog.
        in_title: True when the surface string appears in the article title.
        scope: Occurrence scope (`title`, `body`, or `inferred`).
        first_para_idx: Paragraph index of first body mention (`-1` for title, `None` for inferred).
        para_count: Number of body paragraphs containing the surface string.
        in_cited_para: True when the entity appears inside a model-cited paragraph.
    """

    surface: str
    group: str
    entity_id: str | None = None
    type: str | None = None
    method: str = "semantic"
    in_list: bool = False
    in_title: bool = False
    scope: str = "title"
    first_para_idx: int | None = None
    para_count: int = 0
    in_cited_para: bool = False


@dataclass
class ResolveReport:
    """Lookup statistics of one batch, used to track quality per group.

    Attributes:
        total: Lookup count per group code.
        resolved: Successful lookup count per group code.
    """

    total: dict[str, int] = field(default_factory=dict)
    resolved: dict[str, int] = field(default_factory=dict)

    def add(self, group: str, ok: bool) -> None:
        """Record one lookup.

        Args:
            group: Entity group code.
            ok: Whether the lookup produced a canonical identifier.
        """
        self.total[group] = self.total.get(group, 0) + 1
        if ok:
            self.resolved[group] = self.resolved.get(group, 0) + 1

    def rate(self, group: str) -> float:
        """Compute the lookup success rate of a group.

        Args:
            group: Entity group code.

        Returns:
            Rate from 0 to 1; 0 when the group has no lookups.
        """
        n = self.total.get(group, 0)
        return (self.resolved.get(group, 0) / n) if n else 0.0

    def summary(self) -> list[tuple[str, int, int, float]]:
        """Export per-group statistics for the report.

        Returns:
            Tuples of group code, lookup count, success count and rate.
        """
        return [(g, self.total[g], self.resolved.get(g, 0), self.rate(g))
                for g in sorted(self.total)]


class IntentResolver:
    """Look up canonical identifiers for entities named by the model.

    Attributes:
        reg: Loaded entity registry.
    """

    def __init__(self, registry: EntityRegistry):
        """Build the resolver and the reverse indexes it needs.

        Args:
            registry: Loaded entity registry.
        """
        self.reg = registry
        self._by_type_name: dict[str, dict[str, str]] = {}
        self._by_type_core: dict[str, dict[str, str]] = {}
        for eid, ent in registry.entities.items():
            etype = ent.get("type")
            bucket = self._by_type_name.setdefault(etype, {})
            core_bucket = self._by_type_core.setdefault(etype, {})
            names = [ent.get("canonical_name") or ""] + list(ent.get("aliases") or [])
            for name in names:
                key = _fold(name)
                if key:
                    bucket.setdefault(key, eid)
                if etype in ("TICKER", "UNLISTED_ORG"):
                    core = _strip_corporate_affixes(key)
                    if core:
                        core_bucket.setdefault(core, eid)

    def _lookup(self, surface: str, types: tuple[str, ...],
                *, normalize_corp: bool = False) -> tuple[str | None, str | None]:
        """Look up a string in the allowed entity types in priority order.

        Args:
            surface: Verbatim string named by the model.
            types: Entity types allowed to match, tried in the given order.
            normalize_corp: Also try corporate-affix-stripped matching when exact key misses.

        Returns:
            Pair of identifier and entity type; both None when nothing matches.
        """
        key = _fold(surface)
        if not key:
            return None, None
        for t in types:
            eid = (self._by_type_name.get(t) or {}).get(key)
            if eid:
                return eid, t
        if normalize_corp:
            core = _strip_corporate_affixes(key)
            if core:
                for t in types:
                    eid = self._by_type_name_or_core(t, core)
                    if eid:
                        return eid, t
        return None, None

    def _by_type_name_or_core(self, etype: str, core: str) -> str | None:
        """Look up a stripped corporate brand key against exact and stripped indexes.

        Args:
            etype: Candidate entity type.
            core: Folded brand string with corporate affixes removed.

        Returns:
            Matched `entity_id`, or None.
        """
        return (
            (self._by_type_name.get(etype) or {}).get(core)
            or (self._by_type_core.get(etype) or {}).get(core)
        )

    @staticmethod
    def _locate_scope(out: ResolvedEntity, title: str,
                      paragraphs: list[str] | None,
                      cited_indices: set[int] | None = None) -> None:
        """Populate occurrence scope, paragraph index, and frequency for a resolved entity.

        Args:
            out: Mutable ResolvedEntity instance.
            title: Article title.
            paragraphs: Optional body paragraph strings.
            cited_indices: Optional set of model-cited paragraph indices.
        """
        s = out.surface
        t = title or ""
        if s and s in t:
            out.in_title = True
        elif s and t:
            nt = _normalize_vn_tones(t)
            ns = _normalize_vn_tones(s)
            idx = nt.find(ns)
            if idx >= 0 and len(t) == len(nt):
                out.surface = t[idx:idx + len(s)]
                out.in_title = True

        first_idx: int | None = None
        count = 0
        cited_hit = False
        if s and paragraphs:
            ns = _normalize_vn_tones(s)
            for p_idx, para in enumerate(paragraphs):
                if not para:
                    continue
                if s in para or (ns and ns in _normalize_vn_tones(para)):
                    if first_idx is None:
                        first_idx = p_idx
                    count += 1
                    if cited_indices and p_idx in cited_indices:
                        cited_hit = True

        out.para_count = count
        out.in_cited_para = cited_hit
        if out.in_title:
            out.scope = "title"
            out.first_para_idx = -1
        elif first_idx is not None:
            out.scope = "body"
            out.first_para_idx = first_idx
        elif out.in_list and out.group == "IND":
            out.scope = "inferred"
            out.first_para_idx = None
        else:
            out.scope = "ungrounded"
            out.first_para_idx = None

    def resolve_one(self, surface: str, group: str, *, title: str = "",
                    paragraphs: list[str] | None = None,
                    cited_indices: set[int] | None = None) -> ResolvedEntity:
        """Look up one entity named by the model.

        Args:
            surface: Verbatim string named by the model.
            group: Group code assigned by the model.
            title: Article title, used to tell whether the entity appears in the title.
            paragraphs: Optional body paragraphs used to locate body mentions.
            cited_indices: Optional set of cited paragraph indices.

        Returns:
            Lookup result; `in_list` is False when the entity is not in the catalog.
        """
        surface = (surface or "").strip()
        group = (group or "").strip().upper()
        out = ResolvedEntity(surface=surface, group=group)

        if not surface or group not in VALID_GROUPS or group in GROUPS_WITHOUT_RESOLVER:
            self._locate_scope(out, title, paragraphs, cited_indices)
            return out

        types = GROUP_TYPES[group]

        if group == "TIC":
            code = surface.upper()
            if _CODE_RE.match(code):
                disclosure = _DISCLOSURE_RE.match((title or "").strip())
                exempt = bool(disclosure and disclosure.group(1) == code)
                if code in CODE_STOPLIST and not exempt:
                    self._locate_scope(out, title, paragraphs, cited_indices)
                    return out
                for prefix in ("TICKER", "ETF", "SECURITY_OTHER", "UNLISTED_ORG"):
                    ent = self.reg.entities.get(f"{prefix}:{code}")
                    if ent:
                        out.entity_id = ent["entity_id"]
                        out.type = ent["type"]
                        out.method = "exact_code"
                        out.in_list = True
                        self._locate_scope(out, title, paragraphs, cited_indices)
                        return out
            elif _FUND_CODE_RE.match(code):
                for prefix in ("ETF", "SECURITY_OTHER", "TICKER"):
                    ent = self.reg.entities.get(f"{prefix}:{code}")
                    if ent:
                        out.entity_id = ent["entity_id"]
                        out.type = ent["type"]
                        out.method = "exact_code"
                        out.in_list = True
                        self._locate_scope(out, title, paragraphs, cited_indices)
                        return out
            types = ("TICKER", "ETF", "SECURITY_OTHER", "UNLISTED_ORG")

        eid, etype = self._lookup(surface, types, normalize_corp=(group in ("TIC", "COM")))
        if eid:
            out.entity_id = eid
            out.type = etype
            out.method = "alias" if group in ("TIC", "COM") else "semantic"
            out.in_list = True
        self._locate_scope(out, title, paragraphs, cited_indices)
        return out

    def resolve_many(self, pairs, *, title: str = "",
                     paragraphs: list[str] | None = None,
                     cited_indices: set[int] | None = None,
                     report: ResolveReport | None = None) -> list[ResolvedEntity]:
        """Look up a list of entities and remove duplicates.

        Args:
            pairs: Sequence of `[verbatim string, group code]` pairs emitted by the model.
            title: Article title.
            paragraphs: Optional body paragraphs.
            cited_indices: Optional set of cited paragraph indices.
            report: Optional per-group statistics counter.

        Returns:
            Deduplicated lookup results in order of appearance.
        """
        seen: set[tuple[str, str]] = set()
        seen_eids: set[str] = set()
        out: list[ResolvedEntity] = []
        for pair in pairs or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            surface, group = str(pair[0] or ""), str(pair[1] or "").upper()
            key = (surface.lower(), group)
            if not surface or key in seen:
                continue
            seen.add(key)
            r = self.resolve_one(surface, group, title=title,
                                 paragraphs=paragraphs, cited_indices=cited_indices)
            if report is not None:
                report.add(group, r.in_list)
            out.append(r)
            if r.entity_id:
                seen_eids.add(r.entity_id)
                ent_obj = self.reg.entities.get(r.entity_id) or {}
                parent_id = (ent_obj.get("attributes") or {}).get("parent_entity_id")
                if parent_id and parent_id in self.reg.entities and parent_id not in seen_eids:
                    parent_ent = self.reg.entities[parent_id]
                    seen_eids.add(parent_id)
                    out.append(ResolvedEntity(
                        surface=r.surface,
                        group=r.group,
                        entity_id=parent_ent["entity_id"],
                        type=parent_ent["type"],
                        method="alias",
                        in_list=True,
                        in_title=r.in_title,
                        scope=r.scope,
                        first_para_idx=r.first_para_idx,
                        para_count=r.para_count,
                        in_cited_para=r.in_cited_para,
                    ))
        return out


def reconcile(llm: list[ResolvedEntity], code_ids: set[str]) -> dict[str, str]:
    """Reconcile model results with the deterministic code layer results.

    The labels show end users which entities the model recognized and which the code
    recognized. `LLM_ONLY` is the value unique to the model: sub-brands, industries
    inferred from context, and macro themes without hard keywords.

    Args:
        llm: Resolved entities named by the model.
        code_ids: Identifiers found by the deterministic code layer.

    Returns:
        Dict mapping identifier to the label `BOTH`, `LLM_ONLY` or `CODE_ONLY`.
    """
    llm_ids = {e.entity_id for e in llm if e.entity_id}
    labels: dict[str, str] = {}
    for eid in llm_ids | code_ids:
        if eid in llm_ids and eid in code_ids:
            labels[eid] = "BOTH"
        elif eid in llm_ids:
            labels[eid] = "LLM_ONLY"
        else:
            labels[eid] = "CODE_ONLY"
    return labels
