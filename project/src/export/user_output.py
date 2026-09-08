"""
user_output.py — Ghi output CUỐI cho từng user (CSV theo ngày), gate tối thiểu L1.

Điều kiện ghi 1 article vào final.csv:
    l1_outputs.dod_pass = 1  (L1 agent-reviewed) [BẮT BUỘC]
    agent_outputs.dod_pass = 1 [TÙY CHỌN - nếu chưa có thì để trống ""]

Định tuyến: entity nhận diện (l1_outputs.entities[in_list]) → subscribers_for() → chỉ user
đăng ký entity liên quan (và đang BẬT) mới nhận article.
- Thư mục user (phẳng): users/output/<name>/<YYYY-MM-DD>.csv (deliverable tinh gọn).
- Thư mục audit tập trung (phẳng): users/output/_master/<YYYY-MM-DD>{,_L1,_agent}.csv.

Cột `gold_status` phân biệt GOLD (đã có agent_outputs đạt DoD) vs L1_ONLY (chưa chạm Gold),
để không nhầm "chưa xử lý" với "Gold đã chạy nhưng trường optional rỗng".

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
       a.content_text, a.symbols, a.categories,
       l1.output_json AS l1_json,
       ag.output_json AS agent_json
FROM articles a
JOIN l1_outputs l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
LEFT JOIN (
    SELECT o.article_id, o.output_json
    FROM agent_outputs o
    JOIN (SELECT article_id, MAX(id) AS id FROM agent_outputs
          WHERE dod_pass = 1 GROUP BY article_id) latest
      ON latest.id = o.id
) ag ON ag.article_id = a.url_title_hash
"""

FINAL_COLUMNS = [
    "date", "matched_entities", "title", "summary", "key_points",
    "implication", "impact_area", "time_sensitivity",
    "sentiment", "event_type", "gold_status", "url", "source_domain",
    "article_id", "agent_provider", "model_used",
]
# _master mang thêm cột chẩn đoán; deliverable của user giữ đúng FINAL_COLUMNS.
MASTER_COLUMNS = FINAL_COLUMNS + ["noise_signals"]
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


def _atomic_write_csv(path: Path, columns: list[str], rows: list[dict]) -> tuple[Path, bool]:
    """Ghi CSV atomic. Trả (đường dẫn ĐÃ ghi thật, True nếu phải rơi về snapshot vì file bị khoá).

    Caller BẮT BUỘC đọc cờ thứ hai: khi True, file đích vẫn là bản CŨ (stale) — không được
    log/checkpoint như thể đã giao hàng thành công.
    """
    def _write(f):
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)

    return safe_atomic_write(path, _write, encoding="utf-8-sig", fallback_on_lock=True)


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
        ag = _loads(r.get("agent_json"))
        summ = ag.get("summary") or {}
        impl = ag.get("implication") or {}
        mat = ag.get("materiality") or {}
        sent = ag.get("sentiment") or {}
        meta = ag.get("processing_metadata") or {}
        raw_key_points = summ.get("key_points") or []
        key_points_formatted = "\n".join(f"- {p}" for p in raw_key_points if p) if raw_key_points else ""
        return {
            "date": _row_date(r),
            "matched_entities": self._codes(matched),
            "title": r.get("title") or "",
            "summary": summ.get("abstractive") or "",
            "key_points": key_points_formatted,
            "implication": impl.get("text") or "",
            "impact_area": impl.get("impact_area") or "",
            "time_sensitivity": mat.get("time_sensitivity") or "",
            "sentiment": sent.get("polarity") or sent.get("overall") or "",
            "event_type": ag.get("event_type") or "",
            "gold_status": "GOLD" if r.get("agent_json") else "L1_ONLY",
            "url": r.get("url") or "",
            "source_domain": r.get("source_domain") or "",
            "article_id": r["article_id"],
            "agent_provider": meta.get("agent_provider") or "",
            "model_used": meta.get("model_used") or "",
        }

    def _l1_row(self, r: dict) -> dict:
        d = _loads(r["l1_json"])
        meta = d.get("processing_metadata") or {}
        ents = "; ".join(f"{e.get('entity_id')}({e.get('type')})"
                         for e in (d.get("entities") or []) if e.get("in_list"))
        cats = "; ".join(f"{k}={v}" for k, v in (d.get("categories") or {}).items() if v != "none")
        return {"article_id": r["article_id"], "date": _row_date(r), "title": r.get("title"),
                "entities": ents, "categories": cats,
                # Để TRỐNG khi agent không khai báo — không bịa tên provider.
                "agent_provider": meta.get("agent_provider") or "",
                "model_used": meta.get("model_used") or ""}

    def _agent_row(self, r: dict) -> dict:
        ag = _loads(r.get("agent_json"))
        summ = ag.get("summary") or {}
        impl = ag.get("implication") or {}
        mat = ag.get("materiality") or {}
        sent = ag.get("sentiment") or {}
        meta = ag.get("processing_metadata") or {}
        return {"article_id": r["article_id"], "date": _row_date(r),
                "summary": summ.get("abstractive") or "", "implication": impl.get("text") or "",
                "materiality_score": mat.get("score") if mat.get("score") is not None else "",
                "sentiment": sent.get("polarity") or sent.get("overall") or "",
                "event_type": ag.get("event_type") or "",
                "agent_provider": meta.get("agent_provider") or "",
                "model_used": meta.get("model_used") or ""}

    def _silver_noise_signals(self, matched_eids: set[str], r: dict) -> str:
        """Tín hiệu nhiễu TẤT ĐỊNH từ Silver — chỉ để QUAN SÁT, CHƯA dùng làm gate.

        Ghi vào cột `noise_signals` của `_master/<date>.csv` (không có trong deliverable user).
        Mục đích: gom số liệu thật để sau này chọn ngưỡng, thay vì đoán. Khi đã đủ dữ liệu,
        chuyển tiêu chí nào sang `_passes_noise_filter` là quyết định riêng, có chủ đích.
        """
        title_lower = (r.get("title") or "").lower()
        body_lower = (r.get("content_text") or "").lower()
        symbols = (r.get("symbols") or "").upper()
        alias_title = alias_body = 0
        code_in_symbols = 0
        for eid in matched_eids:
            ent = self.reg.get(eid)
            if not ent:
                continue
            code = (ent.get("code") or "").upper()
            if code and code in {t.strip() for t in symbols.replace(";", ",").split(",")}:
                code_in_symbols += 1
            for a in ent.get("aliases", []):
                if len(a) < 2:
                    continue
                al = a.lower()
                if al in title_lower:
                    alias_title += 1
                alias_body += body_lower.count(al)
        return (f"alias_title={alias_title};alias_body={alias_body};"
                f"body_len={len(body_lower)};code_in_symbols={code_in_symbols};"
                f"cats={(r.get('categories') or '').replace(';', '|')}")

    def _passes_noise_filter(self, matched_eids: set[str], r: dict) -> bool:
        """Lọc rác: nếu chỉ match thực thể diện rộng (MACRO/ASSET), yêu cầu alias xuất hiện ở title.

        KHÔNG đọc bất kỳ trường Gold nào — gate export là L1-only, nên filter cũng phải
        quyết định được khi Gold chưa chạy. Nếu còn dựa `materiality.score` thì bài L1-only
        luôn bị chấm 0 và nới gate chỉ có tác dụng một nửa.
        """
        broad_types = {"MACRO_GEO", "MACRO_THEME", "ASSET_CLASS"}
        matched_types = {self.reg.get(eid)["type"] for eid in matched_eids if self.reg.get(eid)}
        # Nếu có ít nhất 1 entity cụ thể (TICKER, ETF, INDUSTRY, INDEX, EXCHANGE, INSTITUTION) -> Pass luôn
        if any(t not in broad_types for t in matched_types):
            return True
        # Chỉ có broad entities -> alias của entity phải xuất hiện ngay trong title
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
        locked: list[tuple[Path, Path]] = []      # (file đích stale, snapshot đã ghi thay)

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
                has_ag = bool(r.get("agent_json"))
                mrow = self._final_row(r, eset)
                mrow["noise_signals"] = self._silver_noise_signals(eset, r)
                master_bucket.setdefault(d, []).append(
                    (mrow, self._l1_row(r), self._agent_row(r), r["article_id"], has_ag))
            for d, items in master_bucket.items():
                seen, finals, l1s, agents, aids = set(), [], [], [], []
                for frow, l1row, arow, aid, has_ag in items:
                    if aid in seen:
                        continue
                    seen.add(aid); finals.append(frow); l1s.append(l1row); aids.append(aid)
                    if has_ag:
                        agents.append(arow)
                mbase = self.output_root / "_master"
                for mpath, mcols, mrows in ((mbase / f"{d}.csv", MASTER_COLUMNS, finals),
                                            (mbase / f"{d}_L1.csv", L1_COLUMNS, l1s),
                                            (mbase / f"{d}_agent.csv", AGENT_COLUMNS, agents)):
                    actual, was_locked = _atomic_write_csv(mpath, mcols, mrows)
                    if was_locked:
                        locked.append((mpath, actual))

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
            statuses = {row["article_id"]: row["gold_status"] for row in finals}
            new = ckpt.filter_new(user_dir, d, aids)
            upgraded = ckpt.filter_upgraded(user_dir, d, statuses)     # L1_ONLY → GOLD
            actual, was_locked = _atomic_write_csv(file_path, FINAL_COLUMNS, finals)
            n_l1_only = sum(1 for v in statuses.values() if v == "L1_ONLY")
            if was_locked:
                # File đích KHÔNG đổi → chưa giao hàng. Không mark checkpoint, để lần chạy sau
                # ghi lại và vẫn báo đúng new/upgraded thay vì tưởng đã xong.
                locked.append((file_path, actual))
                logger.warning(
                    "user={} date={}: '{}' đang bị khoá bởi tiến trình khác (Excel/OneDrive) → "
                    "file đích VẪN LÀ BẢN CŨ; {} dòng mới nằm ở snapshot '{}'. "
                    "Không mark checkpoint.",
                    user, d, file_path.name, len(finals), actual.name)
            else:
                ckpt.mark_written(user_dir, d, aids, statuses)         # mark SAU khi replace
                logger.info("done user={} date={} rows={} (new={} upgraded={} l1_only={}) file={}",
                            user, d, len(finals), len(new), len(upgraded), n_l1_only, actual.name)
            counts[user] = counts.get(user, 0) + len(finals)

        if locked:
            logger.warning(
                "[FILE LOCK] {} file output KHÔNG cập nhật được vì đang mở ở tiến trình khác: {}. "
                "Đóng file (Excel / Explorer preview / OneDrive đang sync) rồi chạy lại — output "
                "là artifact máy sinh, không mở trong lúc pipeline chạy.",
                len(locked), ", ".join(t.name for t, _ in locked))

        orphan_count = len(rows) - len(matched_article_ids)
        if orphan_count > 0:
            logger.info("diagnostics: {} bài đạt tiêu chuẩn export nhưng không có user nào đăng ký (orphan)", orphan_count)

        if not counts:
            logger.info("done: không có article đạt L1 khớp subscription (date={} days={})", date, days)
            if date == "today":
                all_rows = self.gated_rows(date="all")
                if all_rows:
                    logger.warning(
                        "[LƯU Ý BACKLOG] '--date today' trả về 0 bài, nhưng có {} bài đạt L1 ở các ngày trước "
                        "(gần nhất: {}). Gợi ý: chạy với --days 30 hoặc --date all.",
                        len(all_rows), _row_date(all_rows[-1])
                    )
        return counts
