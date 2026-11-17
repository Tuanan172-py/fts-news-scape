"""Admit into the Research database only articles that completed every Article Lane step and pass record validation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.agent.article_contract import SENTIMENT_MAP, TIME_MAP, analyzed_l1_sql

GATE_VERSION = "research-gate/1"

SENTIMENTS = frozenset({"positive", "negative", "neutral"})
TIME_SENSITIVITIES = frozenset({"urgent", "today", "this_week", "this_month", "archive"})

# Stage 1 of the gate: an article is a candidate only when both business layers passed the
# DoD gate. Content layer: newest `agent_outputs` row with dod_pass = 1. Entity layer: an
# `l1_outputs` row that passed DoD and is not code-first (ADR 0010 D4). Inherited copies
# (ADR 0016) carry both layers with dod_pass = 1 and therefore qualify.
_CANDIDATES_SQL = f"""
SELECT l1.article_id, ag.ag_id, l1.id
FROM l1_outputs l1
JOIN articles a ON a.url_title_hash = l1.article_id
JOIN (SELECT article_id, MAX(id) AS ag_id FROM agent_outputs
      WHERE dod_pass = 1 GROUP BY article_id) ag ON ag.article_id = l1.article_id
WHERE {analyzed_l1_sql('l1')}
"""

_DETAIL_SQL = """
SELECT a.url_title_hash, a.url, a.title, a.source_domain, a.published_at, a.fetched_at,
       a.symbols, a.categories,
       ag.id, ag.raw_sha256, ag.output_json, ag.agent_provider, ag.model_used, ag.created_at,
       l1.id, l1.output_json, l1.l1_source, l1.created_at
FROM articles a
JOIN agent_outputs ag ON ag.id = ?
JOIN l1_outputs l1 ON l1.id = ?
WHERE a.url_title_hash = ?
"""


@dataclass
class GatedEntity:
    """Entity mention admitted with its article.

    Attributes:
        surface: Text as it appears in the title or body.
        entity_id: Catalog id, or None when outside the catalog.
        type: Entity type such as TICKER or INDEX.
        method: Recognition method: exact_code, alias or semantic.
        in_list: Whether the entity maps to the catalog.
        confidence: Model confidence, if given.
        scope: Occurrence scope (`title`, `body`, or `inferred`).
        role: Salience role (`primary` or `mentioned`).
        provenance: Reconciliation provenance (`BOTH`, `LLM_ONLY`, or `CODE_ONLY`).
        confidence_tier: Confidence tier (`HIGH`, `MEDIUM`, or `LOW`).
        first_para_idx: Paragraph index (`-1` for title, `>= 0` for body, `None` for inferred).
    """

    surface: str
    entity_id: str | None
    type: str
    method: str
    in_list: bool
    confidence: float | None
    scope: str = "title"
    role: str = "primary"
    provenance: str = "BOTH"
    confidence_tier: str = "HIGH"
    first_para_idx: int | None = None


@dataclass
class GatedArticle:
    """Article record that passed every gate check, in Research database shape.

    Attributes:
        article_id: `url_title_hash` of the article.
        fingerprint: (agent_outputs.id, l1_outputs.id) the record was built from.
        values: Column values of the Research `articles` table.
        entities: Entity mentions of the article.
        unlisted_candidates: Out-of-catalog candidate surfaces extracted by the model.
    """

    article_id: str
    fingerprint: tuple[int, int]
    values: dict[str, Any]
    entities: list[GatedEntity] = field(default_factory=list)
    unlisted_candidates: list[str] = field(default_factory=list)


@dataclass
class Rejection:
    """Candidate that failed record validation.

    Attributes:
        article_id: `url_title_hash` of the article.
        reasons: Validation failures.
    """

    article_id: str
    reasons: list[str]


def passing_fingerprints(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    """List every article whose two analysis layers passed the DoD gate.

    Args:
        conn: Read-only connection to the operational database.

    Returns:
        Dict article_id -> (agent_outputs.id, l1_outputs.id).
    """
    return {r[0]: (int(r[1]), int(r[2])) for r in conn.execute(_CANDIDATES_SQL)}


def _loads(raw: str | None) -> Any:
    """Parse a JSON string, returning None on any failure.

    Args:
        raw: JSON text.

    Returns:
        Parsed value, or None.
    """
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _text(value: Any, *nested_keys: str) -> str:
    """Return a stripped string, unwrapping a dict through the first matching key.

    Args:
        value: String or dict value.
        *nested_keys: Keys tried when the value is a dict.

    Returns:
        Stripped string, or an empty string.
    """
    if isinstance(value, dict):
        value = next((value[k] for k in nested_keys if isinstance(value.get(k), str)), "")
    return value.strip() if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    """Normalize a list of strings or of dicts holding a quote to a list of non-empty strings.

    Args:
        value: Raw list value.

    Returns:
        Non-empty stripped strings; an empty list when the value is not a list.
    """
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        s = _text(item, "text", "quote", "paragraph")
        if s:
            out.append(s)
    return out


def validate_row(row: tuple) -> tuple[GatedArticle | None, list[str]]:
    """Validate one joined candidate row and build its Research record.

    Args:
        row: Row of `_DETAIL_SQL`.

    Returns:
        (record, []) when every check passes, otherwise (None, reasons).
    """
    (art_id, url, title, domain, pub_at, fetch_at, symbols, categories,
     ag_id, raw_sha, ag_json, ag_provider, ag_model, ag_created,
     l1_id, l1_json, l1_source, l1_created) = row
    reasons: list[str] = []

    if not (url or "").strip():
        reasons.append("article.url empty")
    if not (title or "").strip():
        reasons.append("article.title empty")

    ag = _loads(ag_json)
    if not isinstance(ag, dict):
        reasons.append("agent_output not a JSON object")
        ag = {}
    l1 = _loads(l1_json)
    if not isinstance(l1, dict):
        reasons.append("l1_output not a JSON object")
        l1 = {}

    if ag.get("article_id") not in (None, "", art_id):
        reasons.append("agent_output.article_id mismatch")
    if l1.get("article_id") not in (None, "", art_id):
        reasons.append("l1_output.article_id mismatch")

    summary = _text(ag.get("summary", ag.get("s")), "abstractive", "text")
    key_points = _str_list(ag.get("key_points", ag.get("k")))
    implication = _text(ag.get("implication", ag.get("im")), "text")
    sentiment_raw = _text(ag.get("sentiment", ag.get("sn")))
    sentiment = SENTIMENT_MAP.get(sentiment_raw, sentiment_raw)
    ts_raw = _text(ag.get("time_sensitivity", ag.get("ts")))
    time_sens = TIME_MAP.get(ts_raw, ts_raw)
    citations = _str_list(ag.get("citations", ag.get("c")))

    if not summary:
        reasons.append("summary empty")
    if not key_points:
        reasons.append("key_points empty")
    if not implication:
        reasons.append("implication empty")
    if sentiment not in SENTIMENTS:
        reasons.append(f"sentiment invalid: {sentiment_raw!r}")
    if time_sens not in TIME_SENSITIVITIES:
        reasons.append(f"time_sensitivity invalid: {ts_raw!r}")
    if not citations:
        reasons.append("citations empty")

    raw_entities = l1.get("entities")
    if not isinstance(raw_entities, list):
        reasons.append("l1_output.entities not a list")
        raw_entities = []
    meta_labels = ((l1.get("processing_metadata") or {}).get("intent_source") or {})
    if not isinstance(meta_labels, dict):
        meta_labels = {}
    entities = []
    for ent in raw_entities:
        if not isinstance(ent, dict):
            reasons.append("l1_output.entities item not an object")
            continue
        conf = ent.get("confidence")
        eid = _text(ent.get("entity_id")) or None
        in_list_val = bool(ent.get("in_list"))
        scope_val = _text(ent.get("scope")) or "title"
        prov_val = (
            _text(ent.get("provenance"))
            or (str(meta_labels.get(eid) or "").strip() if eid else "")
            or ("BOTH" if in_list_val else "LLM_ONLY")
        )
        role_val = _text(ent.get("role")) or ("mentioned" if prov_val == "CODE_ONLY" else "primary")
        tier_val = _text(ent.get("confidence_tier")) or (
            "LOW" if prov_val == "CODE_ONLY" else ("HIGH" if role_val == "primary" else "MEDIUM")
        )
        fpi_raw = ent.get("first_para_idx")
        fpi_val = (
            int(fpi_raw)
            if isinstance(fpi_raw, int) and not isinstance(fpi_raw, bool)
            else (-1 if scope_val == "title" else None)
        )
        entities.append(GatedEntity(
            surface=_text(ent.get("surface")),
            entity_id=eid,
            type=_text(ent.get("type")) or "UNKNOWN",
            method=_text(ent.get("method")),
            in_list=in_list_val,
            confidence=float(conf) if isinstance(conf, (int, float)) else None,
            scope=scope_val,
            role=role_val,
            provenance=prov_val,
            confidence_tier=tier_val,
            first_para_idx=fpi_val,
        ))
    unlisted_candidates = _str_list(l1.get("unlisted_candidates"))

    if reasons:
        return None, reasons

    published = (pub_at or "").strip() or (fetch_at or "")
    values = {
        "article_id": art_id,
        "url": url.strip(),
        "title": title.strip(),
        "source_domain": domain or "",
        "published_at": pub_at or None,
        "fetched_at": fetch_at,
        "published_date": published[:10] or None,
        "summary": summary,
        "key_points_json": json.dumps(key_points, ensure_ascii=False),
        "implication": implication,
        "sentiment": sentiment,
        "time_sensitivity": time_sens,
        "citations_json": json.dumps(citations, ensure_ascii=False),
        "symbols": symbols or "",
        "categories": categories or "",
        "raw_sha256": raw_sha or "",
        "analysis_provider": ag_provider or "",
        "analysis_model": ag_model or "",
        "analysis_at": ag_created,
        "entity_at": l1_created,
        "entity_source": l1_source or "agent",
        "inherited_from": ag.get("inherited_from") or l1.get("inherited_from"),
        "src_agent_output_id": int(ag_id),
        "src_l1_output_id": int(l1_id),
        "gate_version": GATE_VERSION,
    }
    return GatedArticle(art_id, (int(ag_id), int(l1_id)), values, entities, unlisted_candidates), []


def load_and_validate(conn: sqlite3.Connection,
                      targets: Iterable[tuple[str, tuple[int, int]]]
                      ) -> tuple[list[GatedArticle], list[Rejection]]:
    """Load candidate rows and run record validation on each.

    Args:
        conn: Read-only connection to the operational database.
        targets: (article_id, (agent_outputs.id, l1_outputs.id)) pairs to load.

    Returns:
        (accepted records, rejections).
    """
    accepted: list[GatedArticle] = []
    rejected: list[Rejection] = []
    for art_id, (ag_id, l1_id) in targets:
        row = conn.execute(_DETAIL_SQL, (ag_id, l1_id, art_id)).fetchone()
        if row is None:
            rejected.append(Rejection(art_id, ["candidate vanished during load"]))
            continue
        rec, reasons = validate_row(row)
        if rec is None:
            rejected.append(Rejection(art_id, reasons))
        else:
            accepted.append(rec)
    return accepted, rejected
