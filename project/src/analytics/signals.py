"""Dựng các bảng tín hiệu insight phái sinh từ kết quả nhận diện và phân tích của mô hình."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

ENTITY_PREFIXES = ("TICKER:", "IND_GICS3:", "MACRO", "ASSET_CLASS:")
LINK_PREFIXES = ("TICKER:", "IND_GICS3:")
MARKET_CLOSE = (14, 45)
BASELINE_SESSIONS = 20
MIN_BASELINE_SESSIONS = 5
MIN_SAME_WEEKDAY = 4
Z_SD_FLOOR = 0.5
SHIFT_SESSIONS = 5
PROFILE_DAYS = 30
MIN_CO_OCCURRENCE = 3
LOAD_MARGIN_DAYS = 40
MIN_CASCADE_MEMBERS = 3

_SENTIMENT_SCORE = {"positive": 1, "negative": -1, "neutral": 0}


@dataclass
class Art:
    """Một bài đã có kết quả nhận diện đạt, kèm sentiment và vai trò trong cụm."""

    id: str
    source: str
    ts: datetime
    trade_date: date
    entities: frozenset[str]
    sentiment: int | None
    cluster: str
    role: str
    novelty: str | None


def next_session(d: date) -> date:
    """Trả ngày làm việc đầu tiên sau ngày `d`, bỏ qua thứ Bảy và Chủ nhật.

    Args:
        d: Ngày xuất phát.

    Returns:
        Ngày thứ Hai đến thứ Sáu kế tiếp.
    """
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def trade_date_of(ts: datetime) -> date:
    """Xác định phiên giao dịch chịu tác động đầu tiên của một tin.

    Tin đăng sau 14:45 hoặc vào cuối tuần tính cho phiên làm việc kế tiếp. Ngày lễ không được xét.

    Args:
        ts: Thời điểm đăng bài theo giờ Việt Nam.

    Returns:
        Ngày phiên giao dịch.
    """
    d = ts.date()
    if d.weekday() >= 5:
        return next_session(d)
    if (ts.hour, ts.minute) > MARKET_CLOSE:
        return next_session(d)
    return d


def parse_ts(raw: str | None) -> datetime | None:
    """Đọc chuỗi ISO 8601 thành datetime giờ Việt Nam.

    Args:
        raw: Chuỗi thời gian, có hoặc không có múi giờ.

    Returns:
        datetime có múi giờ, hoặc None khi chuỗi rỗng hay sai định dạng.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.astimezone(VN_TZ) if dt.tzinfo else dt.replace(tzinfo=VN_TZ)


def sentiment_score(raw_json: str | None) -> int | None:
    """Đọc sentiment số (+1, 0, -1) từ đầu ra phân tích của mô hình.

    Chấp nhận dạng chuỗi của `agent-output-v2-lean` và dạng đối tượng có `polarity` của bản cũ.

    Args:
        raw_json: Nội dung cột `agent_outputs.output_json`.

    Returns:
        Điểm sentiment, hoặc None khi không có hay không hợp lệ.
    """
    if not raw_json:
        return None
    try:
        val = json.loads(raw_json).get("sentiment")
    except (ValueError, AttributeError):
        return None
    if isinstance(val, dict):
        val = val.get("polarity")
    return _SENTIMENT_SCORE.get(val) if isinstance(val, str) else None


def entity_ids(raw_json: str | None, prefixes: tuple[str, ...] = ENTITY_PREFIXES) -> frozenset[str]:
    """Lấy các mã thực thể thuộc nhóm cho phép từ đầu ra nhận diện của mô hình.

    Args:
        raw_json: Nội dung cột `l1_outputs.output_json`.
        prefixes: Tiền tố mã thực thể được giữ lại.

    Returns:
        Tập entity_id.
    """
    if not raw_json:
        return frozenset()
    try:
        ents = json.loads(raw_json).get("entities") or []
    except (ValueError, AttributeError):
        return frozenset()
    return frozenset(e["entity_id"] for e in ents
                     if isinstance(e, dict) and isinstance(e.get("entity_id"), str)
                     and e["entity_id"].startswith(prefixes))


def zscore(value: float, sample: list[float]) -> float:
    """Tính z-score của `value` so với `sample`, độ lệch chuẩn có sàn.

    Args:
        value: Giá trị cần chuẩn hoá.
        sample: Các giá trị nền.

    Returns:
        (value - trung bình) chia cho max(độ lệch chuẩn, sàn).
    """
    return (value - statistics.fmean(sample)) / max(statistics.pstdev(sample), Z_SD_FLOOR)


def _evidence_novelty(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        val = json.loads(raw).get("novelty")
    except (ValueError, AttributeError):
        return None
    return val if isinstance(val, str) else None


def load_data(conn: sqlite3.Connection, since_day: str) -> tuple[list[Art], Counter]:
    """Đọc các bài đã phân tích đạt và đếm số bài đăng mỗi phiên giao dịch.

    Args:
        conn: Kết nối tới DB vận hành.
        since_day: Ngày ISO `YYYY-MM-DD` là mốc dưới theo thời điểm đăng.

    Returns:
        Bộ (danh sách Art có ít nhất một thực thể, Counter trade_date -> tổng số bài đăng).
    """
    expr = "COALESCE(NULLIF(a.published_at, ''), a.fetched_at)"
    totals: Counter = Counter()
    for (raw,) in conn.execute(f"SELECT {expr} FROM articles a WHERE {expr} >= ?", (since_day,)):
        ts = parse_ts(raw)
        if ts:
            totals[trade_date_of(ts)] += 1
    try:
        rows = conn.execute(f"""
            SELECT a.url_title_hash, a.source_domain, {expr}, l1.output_json, ag.output_json,
                   cm.cluster_id, cm.role, cm.evidence
            FROM articles a
            JOIN l1_outputs l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
                 AND COALESCE(l1.l1_source, 'agent') <> 'code_first'
            LEFT JOIN (SELECT o.article_id, o.output_json FROM agent_outputs o
                       JOIN (SELECT article_id, MAX(id) AS id FROM agent_outputs
                             WHERE dod_pass = 1 GROUP BY article_id) m ON m.id = o.id) ag
                 ON ag.article_id = a.url_title_hash
            LEFT JOIN cluster_members cm ON cm.article_id = a.url_title_hash
            WHERE {expr} >= ?""", (since_day,)).fetchall()
    except sqlite3.OperationalError:
        return [], totals
    arts: list[Art] = []
    for aid, src, raw_ts, l1, ag, cid, role, ev in rows:
        ts = parse_ts(raw_ts)
        ents = entity_ids(l1)
        if ts is None or not ents:
            continue
        arts.append(Art(aid, src, ts, trade_date_of(ts), ents, sentiment_score(ag),
                        cid or f"solo:{aid}", role or "canonical", _evidence_novelty(ev)))
    return arts, totals


def build_source_profile(arts: list[Art], window_end: date,
                         days: int = PROFILE_DAYS) -> list[dict]:
    """Tổng hợp hồ sơ từng nguồn trong cửa sổ `days` ngày kết thúc ở `window_end`.

    `lead_rate` là tỷ lệ bài của nguồn đăng sớm nhất trong cụm trên số bài của nguồn thuộc
    cụm có từ hai nguồn trở lên; None khi nguồn không có bài nào thuộc cụm như vậy.

    Args:
        arts: Các bài đã phân tích.
        window_end: Ngày cuối của cửa sổ.
        days: Độ dài cửa sổ tính bằng ngày.

    Returns:
        Danh sách dòng cho bảng `source_profile`.
    """
    start = window_end - timedelta(days=days - 1)
    win = [a for a in arts if start <= a.ts.date() <= window_end]
    clusters: dict[str, list[Art]] = defaultdict(list)
    for a in win:
        clusters[a.cluster].append(a)
    lead_ids = {min(m, key=lambda x: (x.ts, x.id)).id
                for m in clusters.values() if len({x.source for x in m}) >= 2}
    in_multi = {x.id for m in clusters.values() if len({y.source for y in m}) >= 2 for x in m}
    by_src: dict[str, list[Art]] = defaultdict(list)
    for a in win:
        by_src[a.source].append(a)
    out = []
    for src, items in sorted(by_src.items()):
        scored = [a.sentiment for a in items if a.sentiment is not None]
        multi = [a for a in items if a.id in in_multi]
        out.append({
            "source_domain": src, "window_end": window_end.isoformat(), "n": len(items),
            "pos_rate": sum(1 for s in scored if s > 0) / len(scored) if scored else None,
            "neg_rate": sum(1 for s in scored if s < 0) / len(scored) if scored else None,
            "lead_rate": sum(1 for a in multi if a.id in lead_ids) / len(multi) if multi else None,
            "original_rate": sum(1 for a in items if a.role == "canonical") / len(items)})
    return out


def build_entity_links(arts: list[Art], window_end: date, days: int = PROFILE_DAYS) -> list[dict]:
    """Tính độ liên kết PMI giữa các cặp thực thể cùng xuất hiện trong một bài.

    Args:
        arts: Các bài đã phân tích.
        window_end: Ngày cuối của cửa sổ.
        days: Độ dài cửa sổ tính bằng ngày.

    Returns:
        Danh sách dòng cho bảng `entity_links`, mỗi cặp có `entity_a < entity_b`.
    """
    start = window_end - timedelta(days=days - 1)
    sets = []
    for a in arts:
        if start <= a.ts.date() <= window_end:
            ids = sorted(e for e in a.entities if e.startswith(LINK_PREFIXES))
            if ids:
                sets.append(ids)
    n = len(sets)
    single: Counter = Counter()
    pair: Counter = Counter()
    for ids in sets:
        single.update(ids)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair[(ids[i], ids[j])] += 1
    return [{"entity_a": a, "entity_b": b, "window_end": window_end.isoformat(), "n_co": c,
             "pmi": math.log2(c * n / (single[a] * single[b]))}
            for (a, b), c in sorted(pair.items()) if c >= MIN_CO_OCCURRENCE]


def _source_baseline(profile: list[dict]) -> dict[str, float]:
    return {p["source_domain"]: (p["pos_rate"] or 0.0) - (p["neg_rate"] or 0.0) for p in profile}


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _story_votes(items: list[Art]) -> list[int]:
    by_cluster: dict[str, list[Art]] = defaultdict(list)
    for a in items:
        by_cluster[a.cluster].append(a)
    votes = []
    for members in by_cluster.values():
        ordered = sorted(members, key=lambda x: (x.role != "canonical", x.ts, x.id))
        pick = next((m.sentiment for m in ordered if m.sentiment is not None), None)
        if pick is not None:
            votes.append(pick)
    return votes


def _cascade_minutes(items: list[Art]) -> float | None:
    by_cluster: dict[str, list[Art]] = defaultdict(list)
    for a in items:
        by_cluster[a.cluster].append(a)
    spans = []
    for members in by_cluster.values():
        if len(members) >= MIN_CASCADE_MEMBERS:
            ts = sorted(m.ts for m in members)
            spans.append((ts[MIN_CASCADE_MEMBERS - 1] - ts[0]).total_seconds() / 60.0)
    return _mean_or_none(spans)


def build_signal_daily(arts: list[Art], totals: Counter, profile: list[dict]) -> list[dict]:
    """Tính chỉ số chú ý và sentiment cho từng cặp thực thể và phiên giao dịch.

    Args:
        arts: Các bài đã phân tích, gồm cả phần nền dùng tính z-score.
        totals: Tổng số bài đăng mỗi phiên giao dịch, dùng tính `coverage_pct`.
        profile: Kết quả `build_source_profile`, cung cấp mức sentiment nền của từng nguồn.

    Returns:
        Danh sách dòng cho bảng `signal_daily`, trên mọi phiên có dữ liệu.
    """
    if not arts:
        return []
    base = _source_baseline(profile)
    cell: dict[tuple[str, date], list[Art]] = defaultdict(list)
    day_articles: dict[date, set[str]] = defaultdict(set)
    analysed: Counter = Counter()
    for a in arts:
        day_articles[a.trade_date].add(a.id)
        analysed[a.trade_date] += 1
        for e in a.entities:
            cell[(e, a.trade_date)].append(a)
    first, last = min(d for _, d in cell), max(d for _, d in cell)
    sessions = [first + timedelta(days=i) for i in range((last - first).days + 1)
                if (first + timedelta(days=i)).weekday() < 5]
    counts: dict[str, dict[date, int]] = defaultdict(dict)
    for (e, d), items in cell.items():
        counts[e][d] = len(items)

    rows: dict[tuple[str, date], dict] = {}
    for (e, d), items in sorted(cell.items(), key=lambda kv: kv[0][1]):
        prior = [s for s in sessions if s < d][-BASELINE_SESSIONS:]
        z = None
        if len(prior) >= MIN_BASELINE_SESSIONS:
            same = [s for s in prior if s.weekday() == d.weekday()]
            sample = same if len(same) >= MIN_SAME_WEEKDAY else prior
            z = zscore(len(items), [counts[e].get(s, 0) for s in sample])
        scored = [a for a in items if a.sentiment is not None]
        vol = [a.sentiment for a in scored]
        votes = _story_votes(items)
        by_src: dict[str, list[int]] = defaultdict(list)
        for a in scored:
            by_src[a.source].append(a.sentiment)
        src_means = [statistics.fmean(v) for v in by_src.values()]
        norm = _mean_or_none([a.sentiment - base.get(a.source, 0.0) for a in scored])
        past_norm = [rows[(e, s)]["net_sent_norm"] for s in sessions
                     if s < d and (e, s) in rows and rows[(e, s)]["net_sent_norm"] is not None
                     ][-SHIFT_SESSIONS:]
        stale = sum(1 for a in items
                    if a.role == "copy" or (a.role == "candidate" and a.novelty == "none"))
        total = totals.get(d, 0)
        rows[(e, d)] = {
            "entity_id": e, "trade_date": d.isoformat(), "n_articles": len(items),
            "n_sources": len({a.source for a in items}),
            "n_stories": len({a.cluster for a in items}),
            "share": len(items) / len(day_articles[d]), "ama_z": z,
            "stale_ratio": stale / len(items), "cascade_minutes": _cascade_minutes(items),
            "n_updates": sum(1 for a in items if a.role == "candidate"),
            "net_sent_story": _mean_or_none(votes),
            "net_sent_volume": _mean_or_none(vol), "net_sent_norm": norm,
            "dispersion": statistics.pstdev(src_means) if len(src_means) >= 2 else None,
            "sent_shift": (norm - statistics.fmean(past_norm)) if norm is not None and past_norm
            else None,
            "first_source": min(items, key=lambda a: (a.ts, a.id)).source,
            "coverage_pct": round(100.0 * analysed[d] / total, 1) if total else None}
    return list(rows.values())


def _insert(conn: sqlite3.Connection, table: str, cols: list[str], rows: list[dict]) -> None:
    if rows:
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [tuple(r[c] for c in cols) for r in rows])


SIGNAL_COLS = ["entity_id", "trade_date", "n_articles", "n_sources", "n_stories", "share", "ama_z",
               "stale_ratio", "cascade_minutes", "n_updates", "net_sent_story", "net_sent_volume",
               "net_sent_norm", "dispersion", "sent_shift", "first_source", "coverage_pct", "built_at"]
LINK_COLS = ["entity_a", "entity_b", "window_end", "n_co", "pmi"]
PROFILE_COLS = ["source_domain", "window_end", "n", "pos_rate", "neg_rate", "lead_rate",
                "original_rate"]


def build_all(conn: sqlite3.Connection, today: date | None = None, days: int = 30,
              write: bool = True) -> dict[str, list[dict]]:
    """Dựng lại ba bảng tín hiệu trong cửa sổ `days` ngày và ghi vào DB.

    Xoá các dòng của cửa sổ rồi ghi lại, nên chạy lặp lại cho cùng kết quả.

    Args:
        conn: Kết nối ghi tới DB vận hành. Hàm commit khi `write` là True.
        today: Ngày kết thúc cửa sổ; mặc định là hôm nay theo giờ Việt Nam.
        days: Số ngày của cửa sổ cần dựng lại.
        write: False để chỉ tính, không ghi.

    Returns:
        Từ điển các bảng `signal_daily`, `entity_links`, `source_profile` với danh sách dòng.
    """
    today = today or datetime.now(VN_TZ).date()
    since = today - timedelta(days=days - 1)
    arts, totals = load_data(conn, (since - timedelta(days=LOAD_MARGIN_DAYS)).isoformat())
    profile = build_source_profile(arts, today)
    links = build_entity_links(arts, today)
    built_at = datetime.now(VN_TZ).isoformat(timespec="seconds")
    daily = [{**r, "built_at": built_at} for r in build_signal_daily(arts, totals, profile)
             if r["trade_date"] >= since.isoformat()]
    if write:
        conn.execute("DELETE FROM signal_daily WHERE trade_date >= ?", (since.isoformat(),))
        conn.execute("DELETE FROM entity_links WHERE window_end >= ?", (since.isoformat(),))
        conn.execute("DELETE FROM source_profile WHERE window_end >= ?", (since.isoformat(),))
        _insert(conn, "signal_daily", SIGNAL_COLS, daily)
        _insert(conn, "entity_links", LINK_COLS, links)
        _insert(conn, "source_profile", PROFILE_COLS, profile)
        conn.commit()
    return {"signal_daily": daily, "entity_links": links, "source_profile": profile}
