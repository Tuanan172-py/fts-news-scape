"""Cụm hoá bài trùng lặp theo câu chuyện, tất định, không xoá và không sửa bài (ADR 0016)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

COPY_CONTAINMENT = 0.95       # chép lại: gần như nguyên văn, để trích dẫn kế thừa vẫn đúng
CANDIDATE_CONTAINMENT = 0.4   # cùng sự kiện: viết lại, chồng chữ một phần
CANDIDATE_STRONG = 0.5
MIN_SHINGLES_FOR_MATCH = 40   # bài quá ngắn thì containment không đáng tin
TITLE_OVERLAP_MIN = 0.3
COPY_WINDOW_H = 72.0
CANDIDATE_WINDOW_H = 48.0
SHINGLE_WORDS = 5
MIN_BODY_CHARS = 200
BOILERPLATE_DF_RATIO = 0.02   # shingle xuất hiện ở trên 2% số bài là khuôn mẫu
MAX_POSTING = 200

_WORD = re.compile(r"\w+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_UPPER3 = re.compile(r"\b[A-Z]{3}\b")
_NOT_TICKER = frozenset({
    "CEO", "USD", "GDP", "CPI", "IPO", "ETF", "VND", "EUR", "FED", "WTO", "IMF", "OPEC",
    "ESG", "SME", "FDI", "NHNN", "HDQT", "DHCD", "BCTC", "TTCK", "AI", "PMI", "VAT",
})


@dataclass
class Doc:
    """Bản rút gọn của một bài dùng cho so khớp."""

    id: str
    title: str
    source: str
    ts: float | None
    text: str
    symbols: frozenset[str] = frozenset()
    norm_title: str = ""
    series: str = ""
    body_sha: str = ""
    nums: frozenset[str] = frozenset()
    sig_nums: frozenset[str] = frozenset()
    tickers: frozenset[str] = frozenset()
    shingles: frozenset[int] = frozenset()
    raw_len: int = 0
    extra: dict = field(default_factory=dict)


def _nfc_lower(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").lower())


def normalize_number(tok: str) -> str:
    """Bỏ dấu phân cách nghìn và thập phân để so sánh hai cách viết cùng một số.

    Args:
        tok: Chuỗi số như `10.000` hoặc `7,5`.

    Returns:
        Chuỗi chỉ gồm chữ số.
    """
    return re.sub(r"[.,]", "", tok)


def numbers_of(text: str) -> frozenset[str]:
    """Trích tập số (đã chuẩn hoá) xuất hiện trong văn bản.

    Args:
        text: Văn bản nguồn.

    Returns:
        Tập chuỗi số.
    """
    return frozenset(normalize_number(m) for m in _NUMBER.findall(text or ""))


def significant_numbers(nums: frozenset[str]) -> frozenset[str]:
    """Giữ số mang nghĩa nghiệp vụ: từ 3 chữ số trở lên và không phải năm.

    Args:
        nums: Tập số đã chuẩn hoá.

    Returns:
        Tập con loại bỏ ngày tháng, số thứ tự ngắn và năm 1990 đến 2100.
    """
    return frozenset(n for n in nums if len(n) >= 3 and not (len(n) == 4 and 1990 <= int(n) <= 2100))


def tickers_of(title: str, symbols: frozenset[str]) -> frozenset[str]:
    """Gộp mã CP đã gán cho bài và mã chữ hoa 3 ký tự trong tiêu đề.

    Args:
        title: Tiêu đề bài.
        symbols: Mã CP do bộ cào đã gán vào cột `symbols`.

    Returns:
        Tập mã CP. Dùng để chặn gộp nhầm, không dùng làm kết quả nhận diện.
    """
    found = {t for t in _UPPER3.findall(title or "") if t not in _NOT_TICKER}
    return frozenset(found | set(symbols))


def series_key(norm_title: str) -> str:
    """Khoá chuyên mục định kỳ: tiêu đề chuẩn hoá với mọi số thay bằng `#`.

    Args:
        norm_title: Tiêu đề đã chuẩn hoá chữ thường.

    Returns:
        Khoá; hai bài cùng khoá nhưng khác tiêu đề là hai kỳ khác nhau của một chuyên mục.
    """
    return _NUMBER.sub("#", norm_title)


def shingle_set(text: str, k: int = SHINGLE_WORDS) -> frozenset[int]:
    """Băm các cụm k từ liên tiếp của văn bản thành tập số nguyên 64 bit.

    Args:
        text: Văn bản nguồn.
        k: Độ dài cụm từ.

    Returns:
        Tập băm; rỗng nếu văn bản ngắn hơn k từ.
    """
    words = _WORD.findall(_nfc_lower(text))
    return frozenset(
        int.from_bytes(hashlib.blake2b(" ".join(words[i:i + k]).encode(), digest_size=8).digest(), "big")
        for i in range(max(len(words) - k + 1, 0)))


def make_doc(article_id: str, title: str, source: str, ts: float | None, text: str,
             symbols: frozenset[str] = frozenset()) -> Doc:
    """Dựng Doc từ các trường thô của một bài.

    Args:
        article_id: `url_title_hash` của bài.
        title: Tiêu đề.
        source: Tên miền nguồn.
        ts: Thời điểm đăng dạng epoch giây, hoặc None.
        text: Nội dung văn bản thuần.
        symbols: Mã CP đã gán cho bài.

    Returns:
        Doc đã tính sẵn mọi đặc trưng so khớp.
    """
    norm_title = re.sub(r"\s+", " ", _nfc_lower(title)).strip()
    body = re.sub(r"\s+", " ", _nfc_lower(text)).strip()
    lead = f"{title} {(text or '')[:600]}"
    nums = numbers_of(lead)
    return Doc(
        id=article_id, title=title, source=source, ts=ts, text=text or "", symbols=symbols,
        norm_title=norm_title, series=series_key(norm_title),
        body_sha=hashlib.sha256(body.encode()).hexdigest() if len(body) >= MIN_BODY_CHARS else "",
        nums=nums, sig_nums=significant_numbers(nums),
        tickers=tickers_of(title, symbols), shingles=shingle_set(text or ""), raw_len=len(body))


class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _hours(a: Doc, b: Doc) -> float:
    if a.ts is None or b.ts is None:
        return 0.0
    return abs(a.ts - b.ts) / 3600.0


_DATE_TOKEN = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")


def _same_series_other_issue(a: Doc, b: Doc) -> bool:
    """Hai kỳ khác nhau của một chuyên mục định kỳ.

    Kỳ khác nhau khi cùng khuôn tiêu đề mà khác tiêu đề, hoặc khi cả hai tiêu đề đều ghi ngày
    và hai tập ngày khác nhau (tỷ giá 30/9 so với 02/10).
    """
    if a.norm_title == b.norm_title:
        return False
    da, db = set(_DATE_TOKEN.findall(a.norm_title)), set(_DATE_TOKEN.findall(b.norm_title))
    if da and db and da != db:
        return True
    return bool(a.series) and a.series == b.series and "#" in a.series


def title_overlap(a: Doc, b: Doc) -> float:
    """Độ chồng từ giữa hai tiêu đề theo Jaccard trên tập từ.

    Args:
        a: Bài thứ nhất.
        b: Bài thứ hai.

    Returns:
        Giá trị từ 0 đến 1.
    """
    wa, wb = set(_WORD.findall(a.norm_title)), set(_WORD.findall(b.norm_title))
    return len(wa & wb) / max(len(wa | wb), 1)


def _pick_rep(members: list[Doc]) -> Doc:
    return min(members, key=lambda d: (d.ts if d.ts is not None else float("inf"), -d.raw_len, d.id))


def _pair_scores(docs: list[Doc]) -> dict[tuple[int, int], tuple[float, float, int]]:
    """Tính containment và Jaccard cho các cặp có chung shingle không phải khuôn mẫu."""
    df: Counter = Counter()
    for d in docs:
        df.update(d.shingles)
    limit = max(5, int(BOILERPLATE_DF_RATIO * len(docs)))
    kept = [frozenset(s for s in d.shingles if df[s] <= limit) for d in docs]
    index: dict[int, list[int]] = defaultdict(list)
    for i, sh in enumerate(kept):
        for s in sh:
            index[s].append(i)
    shared: Counter = Counter()
    for posting in index.values():
        if 1 < len(posting) <= MAX_POSTING:
            for x in range(len(posting)):
                for y in range(x + 1, len(posting)):
                    shared[(posting[x], posting[y])] += 1
    out = {}
    for (i, j), n in shared.items():
        union = len(kept[i]) + len(kept[j]) - n
        cont = n / max(min(len(kept[i]), len(kept[j])), 1)
        if min(len(kept[i]), len(kept[j])) < MIN_SHINGLES_FOR_MATCH:
            continue
        out[(i, j)] = (cont, n / max(union, 1), n)
    return out


def _cluster_id(canonical_id: str) -> str:
    return "S" + hashlib.sha1(canonical_id.encode()).hexdigest()[:12]


def build_clusters(docs: list[Doc]) -> list[dict]:
    """Gom bài thành cụm câu chuyện và gán vai trò cho từng bài.

    Vai trò: `canonical` (phân tích đầy đủ), `copy` (kế thừa kết quả của một bài trong
    cùng thành phần chép lại), `candidate` (cùng sự kiện với một cụm khác, chờ chế độ chênh).

    Args:
        docs: Các bài trong cửa sổ cần cụm hoá.

    Returns:
        Danh sách dòng cho `cluster_members`, mỗi dòng có khoá article_id, cluster_id, role,
        method, score và evidence (dict).
    """
    n = len(docs)
    ids = list(range(n))
    copy_uf = _UF(ids)
    copy_edge: dict[int, tuple[float, str]] = {}      # đỉnh -> (điểm, phương pháp) của cạnh đã gộp

    # T0: cùng nội dung chính xác.
    by_sha: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        if d.body_sha:
            by_sha[d.body_sha].append(i)
    for group in by_sha.values():
        for k in group[1:]:
            copy_uf.union(group[0], k)
            copy_edge[k] = (1.0, "sha")

    # T1 và ứng viên T2/T3 từ độ chồng shingle.
    cand_edges: list[tuple[int, int, float, dict]] = []
    for (i, j), (cont, jac, shared) in _pair_scores(docs).items():
        a, b = docs[i], docs[j]
        if cont < CANDIDATE_CONTAINMENT or _same_series_other_issue(a, b):
            continue
        dt = _hours(a, b)
        same_tickers = a.tickers == b.tickers
        if cont >= COPY_CONTAINMENT and dt <= COPY_WINDOW_H and a.nums == b.nums and same_tickers:
            copy_uf.union(i, j)
            copy_edge.setdefault(i, (round(cont, 3), "shingle"))
            copy_edge.setdefault(j, (round(cont, 3), "shingle"))
            continue
        if dt > CANDIDATE_WINDOW_H:
            continue
        shared_t = a.tickers & b.tickers
        shared_n = a.sig_nums & b.sig_nums
        tj = title_overlap(a, b)
        anchored = bool(shared_t) or len(shared_n) >= 2
        strong = cont >= CANDIDATE_STRONG and anchored and (bool(shared_n) or tj >= TITLE_OVERLAP_MIN)
        untagged = not a.tickers and not b.tickers and tj >= TITLE_OVERLAP_MIN
        if strong or untagged:
            cand_edges.append((i, j, round(cont, 3), {
                "containment": round(cont, 3), "jaccard": round(jac, 3), "title_overlap": round(tj, 3),
                "shared_tickers": sorted(shared_t), "shared_numbers": sorted(shared_n)[:6]}))

    # Thành phần chép lại -> đại diện.
    comp_members: dict[int, list[int]] = defaultdict(list)
    for i in ids:
        comp_members[copy_uf.find(i)].append(i)
    rep_of_comp = {c: _pick_rep([docs[i] for i in m]) for c, m in comp_members.items()}
    idx_of = {d.id: i for i, d in enumerate(docs)}
    comp_of = {i: copy_uf.find(i) for i in ids}

    # Cụm câu chuyện: mỗi thành phần chỉ nối vào láng giềng tốt nhất xuất hiện sớm hơn, để một
    # chuỗi cạnh yếu không nối bắc cầu nhiều sự kiện khác nhau của cùng một mã.
    def _order(c: int) -> tuple:
        r = rep_of_comp[c]
        return (r.ts if r.ts is not None else float("inf"), r.id)

    neighbours: dict[int, list[tuple[float, int, dict]]] = defaultdict(list)
    for i, j, score, ev in cand_edges:
        ci, cj = comp_of[i], comp_of[j]
        if ci == cj:
            continue
        later, earlier = (ci, cj) if _order(ci) > _order(cj) else (cj, ci)
        neighbours[later].append((score, earlier, ev))
    story_uf = _UF(list(comp_members))
    best_anchor: dict[int, tuple[float, int, dict]] = {}
    for c, options in neighbours.items():
        score, parent, ev = max(options, key=lambda o: o[0])
        story_uf.union(parent, c)
        best_anchor[c] = (score, parent, ev)

    stories: dict[int, list[int]] = defaultdict(list)
    for c in comp_members:
        stories[story_uf.find(c)].append(c)

    series_groups: Counter = Counter(d.series for d in docs if "#" in d.series)
    now = datetime.now(VN_TZ).isoformat(timespec="seconds")
    rows: list[dict] = []
    for comps in stories.values():
        reps = {c: rep_of_comp[c] for c in comps}
        canon_comp = min(comps, key=lambda c: (
            reps[c].ts if reps[c].ts is not None else float("inf"), -reps[c].raw_len, reps[c].id))
        canonical = reps[canon_comp]
        cid = _cluster_id(canonical.id)
        for c in comps:
            rep = reps[c]
            for i in comp_members[c]:
                d = docs[i]
                if d.id == rep.id:
                    if c == canon_comp:
                        role, method, score, ev = "canonical", "single", None, {}
                        if series_groups.get(d.series, 0) > 1:
                            method, ev = "series", {"series_key": d.series}
                    else:
                        score, anchor_c, ev = best_anchor.get(c, (None, canon_comp, {}))
                        ev = {**ev, "same_event_as": rep_of_comp[anchor_c].id}
                        role, method = "candidate", "shingle"
                else:
                    sc, how = copy_edge.get(i, (1.0, "sha"))
                    role, method, score = "copy", how, sc
                    ev = {"inherit_from": rep.id}
                rows.append({"article_id": d.id, "cluster_id": cid, "role": role, "method": method,
                             "score": score, "evidence": ev, "decided_by": "code", "decided_at": now})
    return rows


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)).timestamp()


def _symbols(raw) -> frozenset[str]:
    if not raw:
        return frozenset()
    try:
        val = json.loads(raw)
        return frozenset(str(x).upper() for x in val) if isinstance(val, list) else frozenset()
    except (ValueError, TypeError):
        return frozenset(s.strip().upper() for s in str(raw).split(",") if s.strip())


def load_docs(conn: sqlite3.Connection, since_day: str) -> list[Doc]:
    """Đọc các bài có nội dung từ ngày `since_day` trở đi để cụm hoá.

    Args:
        conn: Kết nối tới DB vận hành.
        since_day: Ngày ISO `YYYY-MM-DD` là mốc dưới theo thời điểm đăng hoặc thu thập.

    Returns:
        Danh sách Doc, đã bỏ bài không có nội dung.
    """
    rows = conn.execute(
        "SELECT url_title_hash, title, source_domain, published_at, fetched_at, content_text, symbols "
        "FROM articles WHERE COALESCE(NULLIF(published_at,''), fetched_at) >= ? "
        "AND content_text IS NOT NULL AND length(content_text) > 0", (since_day,)).fetchall()
    return [make_doc(r[0], r[1], r[2], _epoch(r[3]) or _epoch(r[4]), r[5], _symbols(r[6]))
            for r in rows]


def write_clusters(conn: sqlite3.Connection, rows: list[dict], docs: list[Doc]) -> dict[str, int]:
    """Ghi cụm vào `cluster_members` và `story_clusters`, xoá cụm mồ côi.

    Args:
        conn: Kết nối ghi tới DB vận hành. Hàm commit khi xong.
        rows: Kết quả của `build_clusters`.
        docs: Các Doc đã dùng để dựng cụm, dùng tính số nguồn và mốc thời gian.

    Returns:
        Đếm theo vai trò và số cụm.
    """
    by_id = {d.id: d for d in docs}
    now = datetime.now(VN_TZ).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO cluster_members (article_id, cluster_id, role, method, score, evidence, "
        "decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(article_id) DO UPDATE SET cluster_id=excluded.cluster_id, role=excluded.role, "
        "method=excluded.method, score=excluded.score, evidence=excluded.evidence, "
        "decided_by=excluded.decided_by, decided_at=excluded.decided_at",
        [(r["article_id"], r["cluster_id"], r["role"], r["method"], r["score"],
          json.dumps(r["evidence"], ensure_ascii=False), r["decided_by"], r["decided_at"])
         for r in rows])
    clusters: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(r)
    for cid, members in clusters.items():
        canon = next(m for m in members if m["role"] == "canonical")
        stamps = [by_id[m["article_id"]].ts for m in members if by_id[m["article_id"]].ts is not None]
        iso = lambda t: datetime.fromtimestamp(t, VN_TZ).isoformat(timespec="seconds") if t else None
        conn.execute(
            "INSERT INTO story_clusters (cluster_id, canonical_id, first_seen_at, last_seen_at, "
            "n_members, n_sources, built_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(cluster_id) DO UPDATE SET canonical_id=excluded.canonical_id, "
            "first_seen_at=excluded.first_seen_at, last_seen_at=excluded.last_seen_at, "
            "n_members=excluded.n_members, n_sources=excluded.n_sources, built_at=excluded.built_at",
            (cid, canon["article_id"], iso(min(stamps)) if stamps else None,
             iso(max(stamps)) if stamps else None, len(members),
             len({by_id[m["article_id"]].source for m in members}), now))
    conn.execute("DELETE FROM story_clusters WHERE cluster_id NOT IN "
                 "(SELECT DISTINCT cluster_id FROM cluster_members)")
    conn.commit()
    roles = Counter(r["role"] for r in rows)
    return {"clusters": len(clusters), **{k: roles.get(k, 0) for k in ("canonical", "copy", "candidate")},
            "series": sum(1 for r in rows if r["method"] == "series")}


def run(conn: sqlite3.Connection, days: int = 3, today: datetime | None = None) -> dict[str, int]:
    """Cụm hoá các bài của `days` ngày gần nhất và ghi kết quả.

    Args:
        conn: Kết nối ghi tới DB vận hành.
        days: Số ngày gần nhất, tính cả hôm nay.
        today: Thời điểm hiện tại; mặc định lấy từ đồng hồ.

    Returns:
        Thống kê từ `write_clusters` kèm `docs`.
    """
    today = today or datetime.now(VN_TZ)
    since = (today - timedelta(days=days - 1)).date().isoformat()
    docs = load_docs(conn, since)
    stats = write_clusters(conn, build_clusters(docs), docs)
    return {"docs": len(docs), **stats}
