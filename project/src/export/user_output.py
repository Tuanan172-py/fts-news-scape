"""
user_output.py — Ghi output CUỐI cho từng user (CSV theo ngày), gate "đủ 2 layer".

Điều kiện ghi 1 article vào final.csv (CHỐT 2026-08-18):
    l1_outputs.dod_pass = 1  (L1 agent-reviewed)  AND  agent_outputs.dod_pass = 1

Định tuyến: entity nhận diện (l1_outputs.entities[in_list]) → subscribers_for() → chỉ user
đăng ký entity liên quan (và đang BẬT) mới nhận article. 3 file/ngày để tránh I/O coupling:
    users/output/<name>/<YYYY-MM-DD>/{L1.csv, agent.csv, final.csv}
final.csv = bản gated deliverable; L1.csv/agent.csv = dump từng layer (audit).

Idempotent: rewrite toàn tập per (user, date) + checkpoint theo article_id (crash-safe).
Không notify — chỉ log "done".
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.core.models import VN_TZ
from src.export import checkpoint as ckpt
from src.users.compile import DEFAULT_OUTPUT_ROOT

_GATED_SQL = """
SELECT a.url_title_hash AS article_id, a.title, a.url, a.source_domain,
       a.published_at, a.fetched_at,
       l1.output_json AS l1_json, l1.confidence AS l1_confidence,
       ag.output_json AS agent_json, ag.confidence AS agent_confidence
FROM articles a
JOIN l1_outputs    l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1
"""

FINAL_COLUMNS = [
    "article_id", "date", "source_domain", "url", "title", "matched_entities",
    "summary", "key_points", "implication", "impact_area", "materiality_score",
    "time_sensitivity", "sentiment", "event_type", "confidence",
]
L1_COLUMNS = ["article_id", "date", "title", "entities", "l1_confidence", "categories"]
AGENT_COLUMNS = ["article_id", "date", "summary", "implication",
                 "materiality_score", "sentiment", "event_type", "confidence"]

_SAFE = re.compile(r"[^0-9A-Za-z._-]")


def _safe_name(name: str) -> str:
    return _SAFE.sub("_", str(name)) or "_unknown_user"


def _loads(s):
    try:
        return json.loads(s) if s else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _row_date(r: dict) -> str:
    return (r.get("published_at") or r.get("fetched_at") or "")[:10] or "unknown-date"


def _atomic_write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    os.replace(tmp, path)


class UserOutputWriter:
    def __init__(self, store, registry, *, output_root: str | Path = DEFAULT_OUTPUT_ROOT,
                 enabled: set[str] | None = None):
        self.store = store
        self.reg = registry
        self.output_root = Path(output_root)
        self.enabled = set(enabled) if enabled is not None else None  # None = mọi user

    # -- query gated ----------------------------------------------------------
    def gated_rows(self, *, date: str | None = None, days: int | None = None) -> list[dict]:
        conn = self.store.connect()
        try:
            rows = [dict(r) for r in conn.execute(_GATED_SQL)]
        finally:
            conn.close()
        if date:
            d = f"{datetime.now(VN_TZ):%Y-%m-%d}" if date == "today" else date
            rows = [r for r in rows if _row_date(r) == d]
        elif days:
            cutoff = f"{datetime.now(VN_TZ) - timedelta(days=days):%Y-%m-%d}"
            rows = [r for r in rows if _row_date(r) >= cutoff]
        return rows

    # -- flatten --------------------------------------------------------------
    def _entity_ids(self, l1_json: str) -> set[str]:
        d = _loads(l1_json)
        return {e.get("entity_id") for e in (d.get("entities") or [])
                if e.get("in_list") and e.get("entity_id")}

    def _codes(self, entity_ids) -> str:
        out = []
        for eid in sorted(entity_ids):
            e = self.reg.get(eid)
            out.append(e["code"] if e and e.get("code") else eid)
        return "; ".join(out)

    def _final_row(self, r: dict, matched: set[str]) -> dict:
        ag = _loads(r["agent_json"])
        summ, impl, mat = ag.get("summary") or {}, ag.get("implication") or {}, ag.get("materiality") or {}
        sent = ag.get("sentiment") or {}
        return {
            "article_id": r["article_id"], "date": _row_date(r),
            "source_domain": r.get("source_domain"), "url": r.get("url"), "title": r.get("title"),
            "matched_entities": self._codes(matched),
            "summary": summ.get("abstractive"),
            "key_points": "; ".join(summ.get("key_points") or []),
            "implication": impl.get("text"), "impact_area": impl.get("impact_area"),
            "materiality_score": mat.get("score"), "time_sensitivity": mat.get("time_sensitivity"),
            "sentiment": sent.get("polarity") or sent.get("overall"),
            "event_type": ag.get("event_type"), "confidence": r.get("agent_confidence"),
        }

    def _l1_row(self, r: dict) -> dict:
        d = _loads(r["l1_json"])
        ents = "; ".join(f"{e.get('entity_id')}({e.get('type')})"
                         for e in (d.get("entities") or []) if e.get("in_list"))
        cats = "; ".join(f"{k}={v}" for k, v in (d.get("categories") or {}).items() if v != "none")
        return {"article_id": r["article_id"], "date": _row_date(r), "title": r.get("title"),
                "entities": ents, "l1_confidence": r.get("l1_confidence"), "categories": cats}

    def _agent_row(self, r: dict) -> dict:
        ag = _loads(r["agent_json"])
        summ, impl, mat = ag.get("summary") or {}, ag.get("implication") or {}, ag.get("materiality") or {}
        sent = ag.get("sentiment") or {}
        return {"article_id": r["article_id"], "date": _row_date(r),
                "summary": summ.get("abstractive"), "implication": impl.get("text"),
                "materiality_score": mat.get("score"),
                "sentiment": sent.get("polarity") or sent.get("overall"),
                "event_type": ag.get("event_type"), "confidence": r.get("agent_confidence")}

    # -- route + write --------------------------------------------------------
    def write(self, *, date: str | None = None, days: int | None = None) -> dict[str, int]:
        """Gate + route + ghi CSV per (user, date). Trả {user: số dòng final}. Log 'done'."""
        rows = self.gated_rows(date=date, days=days)
        # bucket[(user, date)] = list of (final_row, l1_row, agent_row, article_id)
        bucket: dict[tuple[str, str], list[tuple]] = {}
        for r in rows:
            eset = self._entity_ids(r["l1_json"])
            if not eset:
                continue
            subs = self.reg.subscribers_for(eset)
            if self.enabled is not None:
                subs &= self.enabled
            for user in subs:
                matched = eset & self.reg.resolve_subscription(user)
                if not matched:
                    continue
                key = (user, _row_date(r))
                bucket.setdefault(key, []).append(
                    (self._final_row(r, matched), self._l1_row(r), self._agent_row(r), r["article_id"]))

        counts: dict[str, int] = {}
        for (user, d), items in sorted(bucket.items()):
            # dedupe theo article_id (rewrite toàn tập → idempotent)
            seen, finals, l1s, agents, aids = set(), [], [], [], []
            for frow, l1row, arow, aid in items:
                if aid in seen:
                    continue
                seen.add(aid); finals.append(frow); l1s.append(l1row); agents.append(arow); aids.append(aid)
            base = self.output_root / _safe_name(user) / d
            new = ckpt.filter_new(base.parent, d, aids)
            _atomic_write_csv(base / "L1.csv", L1_COLUMNS, l1s)
            _atomic_write_csv(base / "agent.csv", AGENT_COLUMNS, agents)
            _atomic_write_csv(base / "final.csv", FINAL_COLUMNS, finals)  # deliverable ghi cuối
            ckpt.mark_written(base.parent, d, aids)                       # mark SAU khi replace
            counts[user] = counts.get(user, 0) + len(finals)
            logger.info("done user={} date={} rows={} (new={})", user, d, len(finals), len(new))
        if not counts:
            logger.info("done: không có article đủ 2 layer khớp subscription (date={} days={})", date, days)
        return counts
