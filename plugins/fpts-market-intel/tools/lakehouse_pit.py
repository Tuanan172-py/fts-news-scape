"""Point-in-time helpers for the Lakehouse client: the HOSE trading calendar and the local materialized cache (ADR-0033)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CALENDAR_FILE = CONFIG_DIR / "trading_calendar.json"
CACHE_SCHEMA = "lakehouse-cache/1"
CACHE_TABLES = ("raw_articles", "articles", "article_entities_all")
MAP_START = date(2015, 1, 1)


def load_trading_calendar(path: Path | None = None) -> dict[str, Any]:
    """Read the weekday holiday list of the exchange.

    Args:
        path: Calendar JSON; defaults to `config/trading_calendar.json`.

    Returns:
        Dict with `holidays` (set of dates), `years` (covered years), `unverified` (covered
        years not yet checked against the exchange notice) and `sha` (content hash, empty
        when the file is missing).
    """
    p = path or CALENDAR_FILE
    try:
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return {"holidays": set(), "years": set(), "unverified": set(), "sha": ""}
    holidays: set[date] = set()
    years: set[int] = set()
    unverified: set[int] = set()
    for year, entry in (data.get("years") or {}).items():
        years.add(int(year))
        if not entry.get("verified"):
            unverified.add(int(year))
        for d in entry.get("holidays") or []:
            holidays.add(date.fromisoformat(d))
    return {"holidays": holidays, "years": years, "unverified": unverified,
            "sha": hashlib.sha256(raw).hexdigest()[:16]}


def next_trading_rows(holidays: set[date], start: date = MAP_START,
                      end: date | None = None) -> list[tuple[date, date]]:
    """Map every calendar day to the first trading day on or after it.

    Weekends are always closed; listed holidays are closed too. Years without a holiday
    list therefore map like a weekend-only calendar.

    Args:
        holidays: Weekday holidays.
        start: First day of the map.
        end: Last day of the map; defaults to 400 days after today.

    Returns:
        List of (day, trading day) pairs in ascending order.
    """
    end = end or date.today() + timedelta(days=400)
    rows: list[tuple[date, date]] = []
    d = end + timedelta(days=14)
    nxt = d
    # Walk backwards so each day reuses the answer of the following day.
    while d >= start:
        if d.weekday() < 5 and d not in holidays:
            nxt = d
        if d <= end:
            rows.append((d, nxt))
        d -= timedelta(days=1)
    rows.reverse()
    return rows


def register_trading_map(con: Any, calendar: dict[str, Any]) -> None:
    """Create the temporary table `_trading_map(d, trade_d)` in a DuckDB connection.

    Args:
        con: DuckDB connection.
        calendar: Result of `load_trading_calendar`.
    """
    con.execute("CREATE OR REPLACE TEMP TABLE _trading_map (d DATE, trade_d DATE)")
    con.executemany("INSERT INTO _trading_map VALUES (?, ?)",
                    next_trading_rows(calendar["holidays"]))


def calendar_warnings(calendar: dict[str, Any], years: set[int]) -> list[str]:
    """List calendar gaps that make `trade_date` less reliable for the given years.

    Args:
        calendar: Result of `load_trading_calendar`.
        years: Years the data covers.

    Returns:
        Vietnamese warnings, empty when every year is covered and verified.
    """
    out = []
    missing = sorted(y for y in years if y not in calendar["years"])
    unverified = sorted(y for y in years if y in calendar["unverified"])
    if missing:
        out.append("Lịch nghỉ HOSE chưa có cho năm " + ", ".join(map(str, missing))
                   + "; trade_date các năm này chỉ bỏ qua cuối tuần.")
    if unverified:
        out.append("Lịch nghỉ năm " + ", ".join(map(str, unverified))
                   + " chưa đối chiếu thông báo HOSE (verified=false).")
    return out


def cache_dir() -> Path:
    """Return the local cache directory, outside any synced folder.

    Returns:
        `NEWS_LAKEHOUSE_CACHE_DIR`, else `%LOCALAPPDATA%/fpts-market-intel/cache`, else
        `~/.cache/fpts-market-intel`.
    """
    env = os.environ.get("NEWS_LAKEHOUSE_CACHE_DIR")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "fpts-market-intel" / "cache") if base else \
        Path.home() / ".cache" / "fpts-market-intel"


def _file_sig(path: Path | None) -> list[Any] | None:
    """Return (path, size, mtime) of a file, or None when it is absent.

    Args:
        path: File path.

    Returns:
        Signature list or None.
    """
    if path is None or not path.is_file():
        return None
    st = path.stat()
    return [str(path), st.st_size, st.st_mtime_ns]


def cache_key(root: Path, partitions: list[Path], master_db: Path | None,
              extra: dict[str, Any]) -> str:
    """Compute the cache key of a client session.

    Any change in partition files, the intraday master, the client code, the calendar or
    the session options gives a different key, so a stale cache is never read.

    Args:
        root: Lakehouse root.
        partitions: Parquet partition files.
        master_db: Intraday master database, or None.
        extra: Session options that change the materialized tables.

    Returns:
        Hex key.
    """
    stats = [p.stat() for p in partitions]
    code = [_file_sig(Path(__file__)), _file_sig(Path(__file__).with_name("lakehouse_client.py"))]
    payload = {
        "schema": CACHE_SCHEMA, "root": str(root).lower(), "n": len(stats),
        "size": sum(s.st_size for s in stats),
        "mtime": max((s.st_mtime_ns for s in stats), default=0),
        "master": _file_sig(master_db), "code": code, "extra": extra,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def cache_path(key_root: Path, slot: str = "live") -> Path:
    """Return the cache file of one Lakehouse root and session slot.

    Live sessions and cutoff sessions use separate files, so a point-in-time query does not
    evict the cache of the current view. Each slot holds one key; a new cutoff replaces the
    previous cutoff only.

    Args:
        key_root: Lakehouse root.
        slot: `live` or `cutoff`.

    Returns:
        Path of the DuckDB cache file.
    """
    tag = hashlib.sha256(str(key_root).lower().encode()).hexdigest()[:12]
    suffix = "" if slot == "live" else f"_{slot}"
    return cache_dir() / f"lakehouse_{tag}{suffix}.duckdb"


def attach_cache(con: Any, path: Path, key: str) -> dict[str, str] | None:
    """Attach a cache file read-only and expose its tables as views when the key matches.

    Args:
        con: DuckDB connection.
        path: Cache file.
        key: Expected key.

    Returns:
        The stored meta values when the views now read from the cache, else None.
    """
    if not path.is_file():
        return None
    try:
        con.execute(f"ATTACH '{path.as_posix()}' AS lhcache (READ_ONLY)")
    except Exception:  # noqa: BLE001 — a locked or corrupt cache is just a miss
        return None
    try:
        meta = dict(con.execute("SELECT key, value FROM lhcache._meta").fetchall())
        if meta.get("cache_key") != key:
            con.execute("DETACH lhcache")
            return None
        for name in CACHE_TABLES:
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM lhcache.{name}")
        return meta
    except Exception:  # noqa: BLE001
        try:
            con.execute("DETACH lhcache")
        except Exception:  # noqa: BLE001
            pass
        return None


def save_cache(con: Any, path: Path, key: str, meta: dict[str, Any] | None = None) -> bool:
    """Write the materialized tables of a session into the cache file atomically.

    Args:
        con: DuckDB connection whose `raw_articles`, `articles` and `article_entities_all`
            are built.
        path: Cache file.
        key: Key stored with the tables.
        meta: Extra session values stored as text, for example the intraday delta count.

    Returns:
        True when the cache file was replaced.
    """
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()
        con.execute(f"ATTACH '{tmp.as_posix()}' AS lhout")
        try:
            for name in CACHE_TABLES:
                con.execute(f"CREATE TABLE lhout.{name} AS SELECT * FROM {name}")
            con.execute("CREATE TABLE lhout._meta (key VARCHAR, value VARCHAR)")
            con.executemany("INSERT INTO lhout._meta VALUES (?, ?)",
                            [("cache_key", key)] + [(k, str(v)) for k, v in (meta or {}).items()])
        finally:
            con.execute("DETACH lhout")
        os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001 — another process may hold the file; the cache is optional
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
