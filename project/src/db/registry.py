"""Maintain the URL discovery ledger that records every URL seen before any filter (ADR 0013, rule 10)."""

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
    """Record a URL in the discovery ledger and report whether it is new or only a variant form.

    Args:
        conn: Write connection to the operational DB. The function does not commit.
        url: URL as returned by the source, kept unchanged.
        source_domain: Source domain.
        via: Discovery channel: listing, rss, api, sitemap or reconcile.

    Returns:
        Tuple of (article key, is new article, is a URL form different from the first one seen).
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
    """Check whether the article already has Bronze and an `articles` row.

    Args:
        conn: Connection to the operational DB.
        key: Article key from `url_key`.

    Returns:
        True if the state is captured.
    """
    row = conn.execute(
        "SELECT state FROM discovered_urls WHERE url_canonical=?", (key,)).fetchone()
    return row is not None and row[0] == "captured"


def known_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    """Filter the keys that are already in the captured state.

    Args:
        conn: Connection to the operational DB.
        keys: Article keys to look up.

    Returns:
        Keys already captured.
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
    """Mark a URL as stored in `articles`, creating the row if missing.

    Args:
        conn: Write connection. Call it in the same transaction that writes `articles`.
        url: Article URL.
        source_domain: Source domain.
        article_hash: `url_title_hash` of the article in `articles`.
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
    """Record a failed scrape attempt and change the state when attempts run out.

    Args:
        conn: Write connection.
        key: Article key.
        error: Error description; at most 300 characters are stored.
        gone: True when the source returned 404 or 410.
        max_attempts: Maximum attempts before the state becomes dead_letter.

    Returns:
        New state of the URL.
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
    """List URLs that were discovered but not yet scraped into articles.

    Args:
        conn: Connection to the operational DB with row_factory set to sqlite3.Row.
        source_domain: Restrict to one source; None means every source.
        limit: Maximum number of rows.

    Returns:
        Rows, oldest first.
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
    """Recompute the article key of every row with the current `url_key` and merge rows that share a key.

    Use after `url_key` gains article ID patterns for more sources. Keeps the most advanced
    state (captured over discovered) when two rows share a key.

    Args:
        conn: Write connection. The function does not commit.

    Returns:
        Counts: scanned, rekeyed, merged.
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
    """Fill the discovery ledger from the existing `articles` table when the ledger is empty.

    Args:
        conn: Write connection. The function does not commit.

    Returns:
        Number of rows added.
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
