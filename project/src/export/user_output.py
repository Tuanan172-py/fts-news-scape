"""
user_output.py — Ghi output CUỐI cho từng user (CSV theo ngày), gate "đủ 2 layer".

Điều kiện ghi 1 article vào final.csv (CHỐT 2026-08-18):
    l1_outputs.dod_pass = 1  (L1 agent-reviewed)  AND  agent_outputs.dod_pass = 1

Định tuyến: entity nhận diện (l1_outputs.entities[in_list]) → subscribers_for() → chỉ user
đăng ký entity liên quan (và đang BẬT) mới nhận article.
- Thư mục user: users/output/<name>/<YYYY-MM-DD>/final.csv (deliverable tinh gọn).
- Thư mục audit tập trung: users/output/_master/<YYYY-MM-DD>/{L1.csv, agent.csv, final.csv}.

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
from src.core.staging import safe_atomic_write
from src.export import checkpoint as ckpt
from src.users.compile import DEFAULT_OUTPUT_ROOT

_GATED_SQL = """
SELECT a.url_title_hash AS article_id, a.title, a.url, a.source_domain,
       a.published_at, a.fetched_at,
       l1.output_json AS l1_json,
       ag.output_json AS agent_json
FROM articles a
JOIN l1_outputs    l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1
"""

FINAL_COLUMNS = [
    "date", "matched_entities", "title", "summary", "key_points",
    "implication", "impact_area", "materiality_score", "time_sensitivity",
    "sentiment", "event_type", "url", "source_domain",
    "article_id", "agent_provider", "model_used",
]
L1_COLUMNS = ["article_id", "date", "title", "entities", "categories", "agent_provider", "model_used"]
AGENT_COLUMNS = ["article_id", "date", "summary", "implication",
                 "materiality_score", "sentiment", "event_type",
                 "agent_provider", "model_used"]

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
    def _write(f):
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

    safe_atomic_write(path, _write, encoding="utf-8-sig", fallback_on_lock=True)


class UserOutputWriter:
    def __init__(self, store, registry, *, output_root: str | Path = DEFAULT_OUTPUT_ROOT,
                 enabled: set[str] | None = None):
        self.store = store
        self.reg = registry
        self.output_root = Path(output_root)
        self.enabled = set(enabled) if enabled is not None else None  # None = mọi user

    # -- query gated ----------------------------------------------------------
    def gated_rows(self, *, date: str | None = None, days: int | None = None) -> list[dict]:
        conn = self.store._connect_ro()
        try:
            rows = [dict(r) for r in conn.execute(_GATED_SQL)]
        finally:
            conn.close()
        if date and date != "all":
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
        meta = ag.get("processing_metadata") or {}
        raw_key_points = summ.get("key_points") or []
        key_points_formatted = "\n".join(f"- {p}" for p in raw_key_points if p) if raw_key_points else ""
        return {
            "date": _row_date(r),
            "matched_entities": self._codes(matched),
            "title": r.get("title"),
            "summary": summ.get("abstractive"),
            "key_points": key_points_formatted,
            "implication": impl.get("text"),
            "impact_area": impl.get("impact_area"),
            "materiality_score": mat.get("score"),
            "time_sensitivity": mat.get("time_sensitivity"),
            "sentiment": sent.get("polarity") or sent.get("overall"),
            "event_type": ag.get("event_type"),
            "url": r.get("url"),
            "source_domain": r.get("source_domain"),
            "article_id": r["article_id"],
            "agent_provider": meta.get("agent_provider") or "unknown",
            "model_used": meta.get("model_used") or "unknown",
        }

    def _l1_row(self, r: dict) -> dict:
        d = _loads(r["l1_json"])
        meta = d.get("processing_metadata") or {}
        ents = "; ".join(f"{e.get('entity_id')}({e.get('type')})"
                         for e in (d.get("entities") or []) if e.get("in_list"))
        cats = "; ".join(f"{k}={v}" for k, v in (d.get("categories") or {}).items() if v != "none")
        return {"article_id": r["article_id"], "date": _row_date(r), "title": r.get("title"),
                "entities": ents, "categories": cats,
                "agent_provider": meta.get("agent_provider") or "unknown",
                "model_used": meta.get("model_used") or "unknown"}

    def _agent_row(self, r: dict) -> dict:
        ag = _loads(r["agent_json"])
        summ, impl, mat = ag.get("summary") or {}, ag.get("implication") or {}, ag.get("materiality") or {}
        sent = ag.get("sentiment") or {}
        meta = ag.get("processing_metadata") or {}
        return {"article_id": r["article_id"], "date": _row_date(r),
                "summary": summ.get("abstractive"), "implication": impl.get("text"),
                "materiality_score": mat.get("score"),
                "sentiment": sent.get("polarity") or sent.get("overall"),
                "event_type": ag.get("event_type"),
                "agent_provider": meta.get("agent_provider") or "unknown",
                "model_used": meta.get("model_used") or "unknown"}

    def _passes_noise_filter(self, matched_eids: set[str], r: dict) -> bool:
        """Lọc rác: nếu chỉ match các thực thể diện rộng (MACRO/ASSET), yêu cầu xuất hiện ở title hoặc materiality >= 0.6."""
        broad_types = {"MACRO_GEO", "MACRO_THEME", "ASSET_CLASS"}
        matched_types = {self.reg.get(eid)["type"] for eid in matched_eids if self.reg.get(eid)}
        # Nếu có ít nhất 1 entity cụ thể (TICKER, ETF, INDUSTRY, INDEX, EXCHANGE, INSTITUTION) -> Pass luôn
        if any(t not in broad_types for t in matched_types):
            return True
        # Nếu chỉ có broad entities -> kiểm tra materiality score >= 0.6 (Rule 02 & agent-output-v1 standard)
        ag = _loads(r.get("agent_json"))
        mat_score = (ag.get("materiality") or {}).get("score") or 0
        try:
            if float(mat_score) >= 0.6:
                return True
        except (ValueError, TypeError):
            pass
        # Hoặc alias của entity xuất hiện ngay trong title
        title_lower = (r.get("title") or "").lower()
        for eid in matched_eids:
            ent = self.reg.get(eid)
            if ent:
                for a in ent.get("aliases", []):
                    if len(a) >= 2 and a.lower() in title_lower:
                        return True
        return False

    # -- route + write --------------------------------------------------------
    def write(self, *, date: str | None = None, days: int | None = None,
              write_master: bool = True) -> dict[str, int]:
        """Gate + route + ghi CSV per (user, date). Trả {user: số dòng final}. Log 'done'."""
        rows = self.gated_rows(date=date, days=days)
        # bucket[(user, date)] = list of (final_row, l1_row, agent_row, article_id)
        bucket: dict[tuple[str, str], list[tuple]] = {}
        matched_article_ids: set[str] = set()

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
                if not self._passes_noise_filter(matched, r):
                    continue
                matched_article_ids.add(r["article_id"])
                key = (user, _row_date(r))
                bucket.setdefault(key, []).append(
                    (self._final_row(r, matched), self._l1_row(r), self._agent_row(r), r["article_id"]))


        # Ghi master audit nếu được bật (dạng phẳng: users/output/_master/{YYYY-MM-DD}.csv)
        if write_master and rows:
            master_bucket: dict[str, list[tuple]] = {}
            for r in rows:
                d = _row_date(r)
                eset = self._entity_ids(r["l1_json"])
                master_bucket.setdefault(d, []).append(
                    (self._final_row(r, eset), self._l1_row(r), self._agent_row(r), r["article_id"]))
            for d, items in master_bucket.items():
                seen, finals, l1s, agents, aids = set(), [], [], [], []
                for frow, l1row, arow, aid in items:
                    if aid in seen:
                        continue
                    seen.add(aid); finals.append(frow); l1s.append(l1row); agents.append(arow); aids.append(aid)
                mbase = self.output_root / "_master"
                _atomic_write_csv(mbase / f"{d}.csv", FINAL_COLUMNS, finals)
                _atomic_write_csv(mbase / f"{d}_L1.csv", L1_COLUMNS, l1s)
                _atomic_write_csv(mbase / f"{d}_agent.csv", AGENT_COLUMNS, agents)

        counts: dict[str, int] = {}
        for (user, d), items in sorted(bucket.items()):
            # dedupe theo article_id (rewrite toàn tập → idempotent)
            seen, finals, l1s, agents, aids = set(), [], [], [], []
            for frow, l1row, arow, aid in items:
                if aid in seen:
                    continue
                seen.add(aid); finals.append(frow); l1s.append(l1row); agents.append(arow); aids.append(aid)
            user_dir = self.output_root / _safe_name(user)
            file_path = user_dir / f"{d}.csv"  # deliverable duy nhất và phẳng cho user
            new = ckpt.filter_new(user_dir, d, aids)
            _atomic_write_csv(file_path, FINAL_COLUMNS, finals)
            ckpt.mark_written(user_dir, d, aids)                       # mark SAU khi replace
            counts[user] = counts.get(user, 0) + len(finals)
            logger.info("done user={} date={} rows={} (new={}) file={}", user, d, len(finals), len(new), file_path.name)

        orphan_count = len(rows) - len(matched_article_ids)
        if orphan_count > 0:
            logger.info("diagnostics: {} bài đạt 2 lớp nhưng không có user nào đăng ký (orphan)", orphan_count)

        if not counts:
            logger.info("done: không có article đủ 2 layer khớp subscription (date={} days={})", date, days)
            if date == "today":
                all_rows = self.gated_rows(date="all")
                if all_rows:
                    logger.warning(
                        "[LƯU Ý BACKLOG] '--date today' trả về 0 bài, nhưng có {} bài đạt 2 layer ở các ngày trước "
                        "(gần nhất: {}). Gợi ý: chạy với --days 30 hoặc --date all.",
                        len(all_rows), _row_date(all_rows[-1])
                    )
        return counts
