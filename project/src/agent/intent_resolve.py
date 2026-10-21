"""Map entities named by the model to canonical catalog identifiers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.agent.entities import CODE_STOPLIST, EntityRegistry, _fold

# Business boundary: the model decides which entities an article contains; this module
# only looks up what the model named. It does not detect extra entities, infer, or
# overrule the model; an unresolved name is recorded as outside the catalog. Each group
# code has its own lookup: tickers need exact match with an abbreviation stoplist,
# company names need alias match with morphology guards, closed groups use direct tables.

# Group codes emitted by the model, mapped to the entity types allowed in the catalog lookup.
GROUP_TYPES: dict[str, tuple[str, ...]] = {
    "TIC": ("TICKER",),
    "COM": ("TICKER",),
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
_DISCLOSURE_RE = re.compile(r"^([A-Z0-9]{3})\s*:")


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
    """

    surface: str
    group: str
    entity_id: str | None = None
    type: str | None = None
    method: str = "semantic"
    in_list: bool = False
    in_title: bool = False


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
        for eid, ent in registry.entities.items():
            etype = ent.get("type")
            bucket = self._by_type_name.setdefault(etype, {})
            names = [ent.get("canonical_name") or ""] + list(ent.get("aliases") or [])
            for name in names:
                key = _fold(name)
                if key:
                    bucket.setdefault(key, eid)

    def _lookup(self, surface: str, types: tuple[str, ...]) -> tuple[str | None, str | None]:
        """Look up a string in the allowed entity types in priority order.

        Args:
            surface: Verbatim string named by the model.
            types: Entity types allowed to match, tried in the given order.

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
        return None, None

    def resolve_one(self, surface: str, group: str, *, title: str = "") -> ResolvedEntity:
        """Look up one entity named by the model.

        Args:
            surface: Verbatim string named by the model.
            group: Group code assigned by the model.
            title: Article title, used to tell whether the entity appears in the title.

        Returns:
            Lookup result; `in_list` is False when the entity is not in the catalog.
        """
        surface = (surface or "").strip()
        group = (group or "").strip().upper()
        out = ResolvedEntity(surface=surface, group=group)
        out.in_title = bool(surface) and surface in (title or "")

        if not surface or group not in VALID_GROUPS or group in GROUPS_WITHOUT_RESOLVER:
            return out

        types = GROUP_TYPES[group]

        if group == "TIC":
            code = surface.upper()
            # A three-character code that equals a common abbreviation is accepted only when
            # the article is a disclosure that starts with "CODE:", the convention of the code layer.
            if _CODE_RE.match(code):
                disclosure = _DISCLOSURE_RE.match((title or "").strip())
                exempt = bool(disclosure and disclosure.group(1) == code)
                if code in CODE_STOPLIST and not exempt:
                    return out
                ent = self.reg.entities.get(f"TICKER:{code}")
                if ent:
                    out.entity_id = ent["entity_id"]
                    out.type = ent["type"]
                    out.method = "exact_code"
                    out.in_list = True
                    return out
            # When the model assigned the wrong group, still try the name as a company name.
            types = ("TICKER",)

        eid, etype = self._lookup(surface, types)
        if eid:
            out.entity_id = eid
            out.type = etype
            out.method = "alias" if group in ("TIC", "COM") else "semantic"
            out.in_list = True
        return out

    def resolve_many(self, pairs, *, title: str = "",
                     report: ResolveReport | None = None) -> list[ResolvedEntity]:
        """Look up a list of entities and remove duplicates.

        Args:
            pairs: Sequence of `[verbatim string, group code]` pairs emitted by the model.
            title: Article title.
            report: Optional per-group statistics counter.

        Returns:
            Deduplicated lookup results in order of appearance.
        """
        seen: set[tuple[str, str]] = set()
        out: list[ResolvedEntity] = []
        for pair in pairs or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            surface, group = str(pair[0] or ""), str(pair[1] or "").upper()
            key = (surface.lower(), group)
            if not surface or key in seen:
                continue
            seen.add(key)
            r = self.resolve_one(surface, group, title=title)
            if report is not None:
                report.add(group, r.in_list)
            out.append(r)
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
