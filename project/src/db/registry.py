"""Sổ phát hiện URL: ghi mọi URL thấy được trước mọi bước lọc (ADR 0013, rule 10)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from src.core.urlnorm import url_key

VN_TZ = timezone(timedelta(hours=7))
STATES = ("discovered", "captured", "gone", "dead_letter")


def _now() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def discover(conn: sqlite3.Connection, url: str, source_domain: str,
             via: str = "listing") -> tuple[str, bool, bool]:
    """Ghi một URL vào sổ phát hiện và báo URL này là mới hay chỉ là dạng biến thể.

    Args:
        conn: Kết nối ghi tới DB vận hành. Hàm không commit.
        url: URL như nguồn trả về, giữ nguyên dạng.
        source_domain: Tên miền nguồn.
        via: Kênh phát hiện: listing, rss, api, sitemap hoặc reconcile.

    Returns:
        Bộ (khoá bài, là bài mới, là dạng URL khác với dạng đã thấy đầu tiên).
    """
    key = url_key(url)
    if not key:
        return "", False, False
    now = _now()
    row = conn.execute(
        "SELECT first_url FROM discovered_urls WHERE url_canonical=?", (key,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO discovered_urls (url_canonical, source_domain, first_url, "
            "first_seen_via, first_seen_at, last_seen_at, n_seen, state, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 'discovered', ?)",
            (key, source_domain, url, via, now, now, now))
        return key, True, False
    conn.execute(
        "UPDATE discovered_urls SET last_seen_at=?, n_seen=n_seen+1 WHERE url_canonical=?",
        (now, key))
    is_alias_form = row[0] != url
    if is_alias_form:
        conn.execute(
            "INSERT OR IGNORE INTO url_aliases (url, url_canonical, seen_at) VALUES (?, ?, ?)",
            (url, key, now))
    return key, False, is_alias_form


def is_captured(conn: sqlite3.Connection, key: str) -> bool:
    """Kiểm tra bài đã có Bronze và dòng `articles` hay chưa.

    Args:
        conn: Kết nối tới DB vận hành.
        key: Khoá bài từ `url_key`.

    Returns:
        True nếu trạng thái là captured.
    """
    row = conn.execute(
        "SELECT state FROM discovered_urls WHERE url_canonical=?", (key,)).fetchone()
    return row is not None and row[0] == "captured"


def known_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    """Lọc ra các khoá đã ở trạng thái captured.

    Args:
        conn: Kết nối tới DB vận hành.
        keys: Danh sách khoá bài cần tra.

    Returns:
        Tập khoá đã captured.
    """
    out: set[str] = set()
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        marks = ",".join("?" * len(chunk))
        out.update(r[0] for r in conn.execute(
            f"SELECT url_canonical FROM discovered_urls WHERE state='captured' "
            f"AND url_canonical IN ({marks})", chunk))
    return out


def mark_captured(conn: sqlite3.Connection, url: str, source_domain: str,
                  article_hash: str) -> None:
    """Đánh dấu URL đã thành bài trong `articles`, tạo dòng nếu chưa có.

    Args:
        conn: Kết nối ghi. Gọi trong cùng transaction với việc ghi `articles`.
        url: URL của bài.
        source_domain: Tên miền nguồn.
        article_hash: `url_title_hash` của bài trong `articles`.
    """
    key = url_key(url)
    if not key:
        return
    now = _now()
    conn.execute(
        "INSERT INTO discovered_urls (url_canonical, source_domain, first_url, "
        "first_seen_via, first_seen_at, last_seen_at, n_seen, state, article_hash, updated_at) "
        "VALUES (?, ?, ?, 'listing', ?, ?, 1, 'captured', ?, ?) "
        "ON CONFLICT(url_canonical) DO UPDATE SET state='captured', "
        "article_hash=excluded.article_hash, last_error=NULL, updated_at=excluded.updated_at",
        (key, source_domain, url, now, now, article_hash, now))


def mark_failed(conn: sqlite3.Connection, key: str, error: str, *,
                gone: bool = False, max_attempts: int = 5) -> str:
    """Ghi một lần cào lỗi và chuyển trạng thái khi hết lượt thử.

    Args:
        conn: Kết nối ghi.
        key: Khoá bài.
        error: Mô tả lỗi, tối đa 300 ký tự được lưu.
        gone: True khi nguồn trả 404 hoặc 410.
        max_attempts: Số lần thử tối đa trước khi sang dead_letter.

    Returns:
        Trạng thái mới của URL.
    """
    row = conn.execute(
        "SELECT attempts FROM discovered_urls WHERE url_canonical=?", (key,)).fetchone()
    if row is None:
        return "discovered"
    attempts = row[0] + 1
    state = "gone" if gone else ("dead_letter" if attempts >= max_attempts else "discovered")
    conn.execute(
        "UPDATE discovered_urls SET attempts=?, last_error=?, state=?, updated_at=? "
        "WHERE url_canonical=?", (attempts, error[:300], state, _now(), key))
    return state


def pending(conn: sqlite3.Connection, source_domain: str | None = None,
            limit: int = 200) -> list[sqlite3.Row]:
    """Liệt kê URL đã phát hiện nhưng chưa cào thành bài.

    Args:
        conn: Kết nối tới DB vận hành, row_factory là sqlite3.Row.
        source_domain: Giới hạn theo nguồn; None là mọi nguồn.
        limit: Số dòng tối đa.

    Returns:
        Danh sách dòng, cũ nhất trước.
    """
    sql = ("SELECT url_canonical, source_domain, first_url, attempts, first_seen_via "
           "FROM discovered_urls WHERE state='discovered'")
    args: list = []
    if source_domain:
        sql += " AND source_domain=?"
        args.append(source_domain)
    sql += " ORDER BY first_seen_at LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def rekey(conn: sqlite3.Connection) -> dict[str, int]:
    """Tính lại khoá bài của mọi dòng theo `url_key` hiện hành và gộp các dòng trùng khoá.

    Dùng sau khi `url_key` được mở rộng mẫu mã bài cho thêm nguồn. Giữ trạng thái tiến xa nhất
    (captured hơn discovered) khi hai dòng cùng khoá.

    Args:
        conn: Kết nối ghi. Hàm không commit.

    Returns:
        Đếm: scanned, rekeyed, merged.
    """
    rank = {"captured": 3, "gone": 2, "dead_letter": 1, "discovered": 0}
    rows = conn.execute(
        "SELECT url_canonical, first_url, state, article_hash FROM discovered_urls").fetchall()
    stats = {"scanned": len(rows), "rekeyed": 0, "merged": 0}
    for old_key, first_url, state, article_hash in rows:
        new_key = url_key(first_url)
        if not new_key or new_key == old_key:
            continue
        existing = conn.execute(
            "SELECT state, article_hash FROM discovered_urls WHERE url_canonical=?",
            (new_key,)).fetchone()
        if existing is None:
            conn.execute("UPDATE discovered_urls SET url_canonical=? WHERE url_canonical=?",
                         (new_key, old_key))
            stats["rekeyed"] += 1
        else:
            if rank.get(state, 0) > rank.get(existing[0], 0):
                conn.execute(
                    "UPDATE discovered_urls SET state=?, article_hash=? WHERE url_canonical=?",
                    (state, article_hash, new_key))
            conn.execute("INSERT OR IGNORE INTO url_aliases (url, url_canonical, seen_at) "
                         "VALUES (?, ?, ?)", (first_url, new_key, _now()))
            conn.execute("DELETE FROM discovered_urls WHERE url_canonical=?", (old_key,))
            stats["merged"] += 1
    for url, old_key in conn.execute("SELECT url, url_canonical FROM url_aliases").fetchall():
        new_key = url_key(url)
        if new_key and new_key != old_key:
            conn.execute("UPDATE url_aliases SET url_canonical=? WHERE url=?", (new_key, url))
    return stats


def backfill_from_articles(conn: sqlite3.Connection) -> int:
    """Nạp sổ phát hiện từ bảng `articles` hiện có khi sổ còn trống.

    Args:
        conn: Kết nối ghi. Hàm không commit.

    Returns:
        Số dòng đã thêm.
    """
    if conn.execute("SELECT 1 FROM discovered_urls LIMIT 1").fetchone():
        return 0
    now = _now()
    rows = conn.execute(
        "SELECT url, url_title_hash, source_domain, COALESCE(fetched_at, ?) FROM articles",
        (now,)).fetchall()
    batch = []
    for url, h, dom, fetched in rows:
        key = url_key(url)
        if key:
            batch.append((key, dom, url, fetched, fetched, h, now))
    conn.executemany(
        "INSERT OR IGNORE INTO discovered_urls (url_canonical, source_domain, first_url, "
        "first_seen_via, first_seen_at, last_seen_at, n_seen, state, article_hash, updated_at) "
        "VALUES (?, ?, ?, 'listing', ?, ?, 1, 'captured', ?, ?)", batch)
    return len(batch)
