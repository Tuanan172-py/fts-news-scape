"""Bổ sung nội dung toàn văn và ngày xuất bản cho các bài viết bị trì hoãn bóc tách."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from src.core.config import (
    load_domain_config,
    load_secrets,
    load_settings,
    resolve_source_domain,
)
from src.core.logging import setup_logging
from src.core.models import VN_TZ, now_vn_iso
from src.core.stdio import force_utf8_stdio
from src.crawler.backoff import SourceBackoff
from src.crawler.http_client import HTTPClient
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate
from src.db.store import ArticleStore
from src.pipeline.silver_builder import _html_from_json
from src.processor.extractor import extract_text

# morninger gọi script này qua subprocess với capture_output=True → stdout là pipe, mặc
# định dùng encoding hệ thống (cp1252) và sẽ crash khi in tiếng Việt/emoji.
force_utf8_stdio()

RAW_DIR = "data/raw_html"

DEFAULT_MAX_ATTEMPTS = 5

# Bài đã xác nhận mất vĩnh viễn (nguồn xóa 404/410) hoặc đã thử đủ số lần cho phép —
# không truy đuổi nữa. Thiếu bộ lọc này thì job tự động (mỗi 5 phút) sẽ fetch lại một
# URL đã chết mãi mãi.
_EXCLUDE_DEAD = ("metadata_json NOT LIKE '%\"source_deleted\": true%' "
                 "AND metadata_json NOT LIKE '%\"source_deleted\":true%' "
                 "AND metadata_json NOT LIKE '%\"capture_giveup\": true%' "
                 "AND metadata_json NOT LIKE '%\"capture_giveup\":true%'")

# Bài vượt `max_details_per_cycle` — chưa từng fetch trang chi tiết lần nào.
_DEFERRED_WHERE = ("((metadata_json LIKE '%\"detail_deferred\": true%' "
                   "OR metadata_json LIKE '%\"detail_deferred\":true%') "
                   f"AND {_EXCLUDE_DEAD})")

# Bài ĐÃ fetch nhưng hỏng tạm thời trong lượt capture sống (timeout, 5xx, 403, body
# rỗng). `backfilled_from_bronze` loại bài đã khôi phục xong khỏi vòng quét lại.
_FAILED_WHERE = ("(metadata_json LIKE '%\"capture_status\": \"failed\"%' "
                 "AND metadata_json NOT LIKE '%backfilled_from_bronze%' "
                 f"AND {_EXCLUDE_DEAD})")


def _find_bronze(domain: str, url_title_hash: str,
                 raw_dir: str = RAW_DIR) -> str | None:
    """Tìm file Bronze .html DÙNG ĐƯỢC của bài. None nếu chưa có hoặc không hợp lệ.

    `RawStore.save` vẫn ghi body khi HTTP lỗi (giữ lại để soi), nên một trang 404/500
    cũng sinh file .html. Phải soi sidecar .meta.json để loại chúng — nếu không, lượt
    backfill sau sẽ bóc nội dung TRANG LỖI ra làm nội dung bài. Thiếu sidecar thì chấp
    nhận (artifact cũ hoặc đặt tay).
    """
    hits = sorted(glob.glob(os.path.join(raw_dir, domain, "*",
                                         f"{url_title_hash}.html")))
    for html_path in reversed(hits):      # bản mới nhất trước
        meta_path = html_path[:-len(".html")] + ".meta.json"
        try:
            status = json.loads(
                Path(meta_path).read_text(encoding="utf-8")).get("capture_status")
        except (OSError, ValueError):
            return html_path              # không có/không đọc được sidecar → tin file
        if status in ("ok", "partial"):
            return html_path
    return None


def _content_selector_for(domain_cfg_name: str) -> str:
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return ""
    return (cfg.get("detail", {}) or {}).get("content_selector", "") or ""


def _detail_endpoint(domain_cfg_name: str, row) -> tuple[str, dict]:
    """(url_để_fetch, headers). Mặc định là `articles.url`.

    Nguồn API khai `api.detail_url_template` (vd fireant `/posts/{post_id}`) thì trang
    web chỉ là SPA — phải fetch endpoint API. Template điền từ `metadata` của bài.
    Kèm Bearer token nếu config khai `auth.secret_key`.
    """
    url = row["url"]
    headers: dict = {}
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return url, headers

    template = (cfg.get("api", {}) or {}).get("detail_url_template", "")
    if template:
        try:
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            url = template.format(**meta)
            headers["Accept"] = "application/json, text/plain, */*"
        except (KeyError, IndexError, ValueError):
            url = row["url"]          # thiếu field → quay về URL web, không đoán

    secret_key = (cfg.get("auth", {}) or {}).get("secret_key", "")
    if secret_key:
        token = (load_secrets().get(secret_key) or "").strip()
        if token[:7].lower() == "bearer ":
            token = token[7:].strip()
        if token and not token.startswith("PASTE_"):
            headers["Authorization"] = f"Bearer {token}"
    return url, headers


def _extract_from_bronze(html_path: str, selector: str) -> tuple[str, str]:
    """(content_html, content_text) từ file Bronze. Thuần, không mạng.

    Bronze của nguồn API (vd fireant) là **JSON** chứ không phải HTML → bóc trường HTML
    ra trước, y như `SilverBuilder` làm. Không có bước này thì content_text sẽ nuốt cả
    key JSON và dấu ngoặc.
    """
    try:
        html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("read bronze failed {}: {}", html_path, e)
        return "", ""

    inner = _html_from_json(html)
    if inner is not None:
        html = inner
        selector = ""          # đã là HTML thân bài, không cần cắt selector nữa

    node_html = html
    if selector:
        try:
            from bs4 import BeautifulSoup
            node = BeautifulSoup(html, "lxml").select_one(selector)
            if node is not None and node.get_text(strip=True):
                node_html = str(node)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("selector {} failed on {}: {}", selector, html_path, e)
    return node_html, extract_text(node_html)


_DATE_TEXT_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")


def _date_scope_for(domain_cfg_name: str) -> str:
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return ""
    return (cfg.get("detail", {}) or {}).get("date_scope_selector", "") or ""


def recover_published_at(html_path: str, date_scope: str = "") -> str:
    """Khôi phục published_at TỪ FILE BRONZE. Rỗng nếu không chắc — KHÔNG bịa.

    Thứ tự (generic trước, config sau):
      1. <meta property="article:published_time"> / itemprop="datePublished"
      2. <time datetime="...">
      3. JSON-LD "datePublished"
      4. `date_scope_selector` trong config + text `dd/MM/yyyy HH:mm` (vd baodautu —
         nguồn KHÔNG có metadata ngày nào cả)
    """
    try:
        html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - defensive
        return ""

    for attrs in ({"property": "article:published_time"},
                  {"itemprop": "datePublished"},
                  {"name": "pubdate"}):
        tag = soup.find("meta", attrs=attrs)
        val = (tag.get("content") or "").strip() if tag else ""
        if val:
            return val
    tag = soup.find("time", attrs={"datetime": True})
    if tag and (tag.get("datetime") or "").strip():
        return tag["datetime"].strip()
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()

    if date_scope:
        node = soup.select_one(date_scope)
        if node is not None:
            m = _DATE_TEXT_RE.search(node.get_text(" ", strip=True))
            if m:
                d, mo, y, hh, mm = (int(g) for g in m.groups())
                try:
                    return datetime(y, mo, d, hh, mm,
                                    tzinfo=VN_TZ).isoformat(timespec="seconds")
                except ValueError:
                    return ""
    return ""


def _record_attempt(conn, row, cap: dict, max_attempts: int) -> None:
    """Ghi sổ một lần khôi phục nội dung THẤT BẠI vào `metadata_json` của bài.

    Không ghi sổ thì bài hỏng vĩnh viễn sẽ được chọn lại ở MỌI chu kỳ sau (job tự động
    chạy mỗi 5 phút), vì `_INSERT_SQL` của ArticleStore là `INSERT OR IGNORE` nên row
    đã tồn tại không bao giờ tự cập nhật — bắt buộc phải UPDATE tường minh ở đây.

    Args:
        conn: Kết nối SQLite đang mở.
        row: Dòng bảng `articles` đang xử lý.
        cap: Dict trạng thái capture do `RawStore.save` trả về (rỗng nếu không fetch).
        max_attempts: Số lần thử tối đa trước khi gắn cờ bỏ cuộc.
    """
    meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    retry = meta.setdefault("capture_retry", {})
    retry["attempts"] = int(retry.get("attempts", 0)) + 1
    retry["last_at"] = now_vn_iso()
    retry["last_status"] = cap.get("http_status")
    if cap.get("capture_status") == "deleted_at_source":
        meta["source_deleted"] = True
    elif retry["attempts"] >= max_attempts:
        meta["capture_giveup"] = True
    conn.execute(
        "UPDATE articles SET metadata_json=?, processed_at=? WHERE id=?",
        (json.dumps(meta, ensure_ascii=False), now_vn_iso(), row["id"]))
    conn.commit()


def main(domain: str | None, limit: int, do_fetch: bool, dry_run: bool,
         db_path: str | None = None, raw_dir: str = RAW_DIR,
         dates_only: bool = False, mode: str = "deferred",
         max_attempts: int = DEFAULT_MAX_ATTEMPTS,
         retry_window_hours: int = 0, budget_seconds: int = 0) -> int:
    """db_path/raw_dir override để test cô lập được (mặc định: settings + RAW_DIR).

    Args:
        mode: `deferred` (bài vượt cap), `failed` (bài lỗi tạm thời), `all` (cả hai).
        max_attempts: Số lần thử tối đa trước khi gắn `capture_giveup`.
        retry_window_hours: Chỉ truy đuổi bài có `fetched_at` trong N giờ gần đây;
            0 = không giới hạn (giữ nguyên hành vi backfill thủ công hàng loạt).
        budget_seconds: Trần thời gian chạy; vượt thì dừng SẠCH giữa hai bài và báo cáo
            phần đã làm. 0 = không giới hạn. Cần vì job tự động bị morninger gọi kèm
            timeout — hết giờ mà không tự dừng thì bị giết giữa chừng, mất báo cáo.
    """
    settings = load_settings()
    setup_logging(settings["logging"]["level"], settings["logging"]["dir"])
    store = ArticleStore(db_path or settings["database"]["path"])

    # domain arg nhận CẢ tên config lẫn host (vietnambiz | vietnambiz.vn)
    host = resolve_source_domain(domain) if domain else None
    cfg_name = domain.split(".")[0] if domain else ""
    selector = _content_selector_for(cfg_name) if cfg_name else ""
    date_scope = _date_scope_for(cfg_name) if cfg_name else ""

    conn = store.connect()
    # --dates-only: sửa cột published_at rỗng cho bài ĐÃ có Bronze (không cần còn cờ
    # detail_deferred). Cần vì lần backfill đầu đã gỡ cờ nhưng chưa điền ngày.
    if dates_only:
        where = "WHERE (published_at IS NULL OR published_at = '')"
    elif mode == "failed":
        where = f"WHERE {_FAILED_WHERE}"
    elif mode == "all":
        where = f"WHERE ({_DEFERRED_WHERE} OR {_FAILED_WHERE})"
    else:
        where = f"WHERE {_DEFERRED_WHERE}"
    params: list = []
    if retry_window_hours > 0 and not dates_only:
        cutoff = (datetime.now(VN_TZ)
                  - timedelta(hours=retry_window_hours)).isoformat(timespec="seconds")
        where += " AND fetched_at >= ?"      # ISO offset cố định +07:00 → so sánh chuỗi an toàn
        params.append(cutoff)
    if host:
        where += " AND source_domain = ?"
        params.append(host)
    params.append(limit)
    rows = conn.execute(
        f"SELECT id, url, url_title_hash, source_domain, summary, published_at, "
        f"metadata_json "
        f"FROM articles {where} LIMIT ?", params).fetchall()

    logger.info("{} rows: {} (domain={}, selector={!r}, date_scope={!r})",
                "date-repair" if dates_only else mode,
                len(rows), host or "ALL", selector, date_scope)

    # Không dựng HTTP client/robots khi không có việc. Vẫn PHẢI in một dòng: job im lặng
    # không phân biệt được với job đã chết, và morninger chỉ log dòng stdout cuối cùng.
    if not rows:
        print(f"backfill [{mode}]: candidates=0 (không có việc)")
        conn.close()
        return 0

    raw_store = RawStore(raw_dir)
    http = robots = backoff = None
    if do_fetch:
        http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"],
                          max_retries=settings["http"]["max_retries"])
        robots = RobotsGate(http)
        backoff = SourceBackoff()

    stats = {"from_bronze": 0, "fetched": 0, "no_bronze": 0,
             "empty": 0, "skipped_robots": 0, "failed": 0,
             "date_recovered": 0, "date_missing": 0, "gave_up": 0,
             "budget_stopped": 0}

    started = time.monotonic()
    for r in rows:
        if budget_seconds > 0 and (time.monotonic() - started) >= budget_seconds:
            stats["budget_stopped"] = 1
            logger.info("[backfill] hết ngân sách {}s — dừng sạch, phần còn lại để "
                        "chu kỳ sau", budget_seconds)
            break
        dom = r["source_domain"]
        sel = selector or _content_selector_for(dom.split(".")[0])
        dscope = date_scope or _date_scope_for(dom.split(".")[0])
        html_path = _find_bronze(dom, r["url_title_hash"], raw_dir)

        if html_path is None:
            if not do_fetch:
                stats["no_bronze"] += 1
                continue
            # Không có Bronze → PHẢI ghi Bronze trước, không bao giờ ghi content trần.
            # Nguồn API (vd fireant): `articles.url` là trang WEB (SPA, không có body) —
            # phải fetch ENDPOINT API mới ra nội dung. Lấy từ api.detail_url_template.
            fetch_url, extra_headers = _detail_endpoint(dom.split(".")[0], r)
            if robots is not None and not robots.allowed(fetch_url):
                stats["skipped_robots"] += 1
                continue
            if backoff is not None:
                backoff.before_fetch(dom)
            resp = http.get_response(fetch_url, headers=extra_headers or None,
                                     timeout=settings["http"]["timeout"])
            cap = raw_store.save(dom, fetch_url, r["url_title_hash"], resp,
                                 fetched_at=now_vn_iso())
            if backoff is not None:
                backoff.observe(dom, cap.get("http_status"))
            if cap.get("capture_status") not in ("ok", "partial") \
                    or not (cap.get("html_path") or "") \
                    or not os.path.exists(cap.get("html_path") or ""):
                stats["failed"] += 1
                if not dry_run:
                    _record_attempt(conn, r, cap, max_attempts)
                    if cap.get("capture_status") == "deleted_at_source":
                        stats["gave_up"] += 1
                continue
            html_path = cap["html_path"]
            stats["fetched"] += 1
        else:
            stats["from_bronze"] += 1

        if dates_only:
            recovered = recover_published_at(html_path, dscope)
            if not recovered:
                stats["date_missing"] += 1
                continue
            stats["date_recovered"] += 1
            if dry_run:
                continue
            conn.execute("UPDATE articles SET published_at=?, processed_at=? "
                         "WHERE id=?", (recovered, now_vn_iso(), r["id"]))
            conn.commit()
            continue

        content_html, content_text = _extract_from_bronze(html_path, sel)
        if not content_text.strip():
            # Bronze có nhưng bóc ra rỗng (selector lệch / trang chặn). Vẫn tính là một
            # lần thử để bài hỏng vĩnh viễn không kẹt lại trong hàng đợi mãi.
            stats["empty"] += 1
            if not dry_run:
                _record_attempt(conn, r, {}, max_attempts)
            continue

        if dry_run:
            continue

        # published_at: nguồn như baodautu chỉ có ngày ở TRANG DETAIL, mà bài deferred
        # chưa từng qua enrich() → cột rỗng. Khôi phục TỪ BRONZE, không bịa.
        published = (r["published_at"] or "").strip()
        if not published:
            published = recover_published_at(html_path, dscope)
            if published:
                stats["date_recovered"] += 1
            else:
                stats["date_missing"] += 1

        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        meta.pop("detail_deferred", None)
        meta.pop("capture_retry", None)          # khôi phục xong → xoá sổ theo dõi
        meta["backfilled_from_bronze"] = html_path.replace("\\", "/")
        conn.execute(
            "UPDATE articles SET content_html=?, content_text=?, published_at=?, "
            "processed_at=?, metadata_json=? WHERE id=?",
            (content_html, content_text, published, now_vn_iso(),
             json.dumps(meta, ensure_ascii=False), r["id"]))
        conn.commit()

    conn.close()
    updated = stats["from_bronze"] + stats["fetched"] - stats["empty"]
    logger.info("backfill done{}: updated~{} {}",
                " (DRY RUN)" if dry_run else "", max(updated, 0), stats)
    print(f"backfill{' (dry-run)' if dry_run else ''} [{mode}]: "
          f"candidates={len(rows)} from_bronze={stats['from_bronze']} "
          f"fetched={stats['fetched']} no_bronze={stats['no_bronze']} "
          f"empty={stats['empty']} skipped_robots={stats['skipped_robots']} "
          f"failed={stats['failed']} deleted_at_source={stats['gave_up']} "
          f"date_recovered={stats['date_recovered']} "
          f"date_missing={stats['date_missing']} "
          f"budget_stopped={stats['budget_stopped']}")
    if stats["no_bronze"]:
        print(f"  ⚠️  {stats['no_bronze']} bài CHƯA có Bronze — chạy "
              f"`python scripts/refresh_watchlist.py <n> {host or '<host>'}` trước, "
              f"hoặc thêm --fetch.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    p.add_argument("domain", nargs="?", default=None,
                   help="tên config (vietnambiz) hoặc host (vietnambiz.vn)")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--fetch", action="store_true",
                   help="cho phép fetch (ghi Bronze) khi bài chưa có artifact")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dates-only", action="store_true",
                   help="chỉ sửa published_at rỗng (bài đã có Bronze), không đụng content")
    p.add_argument("--mode", choices=["deferred", "failed", "all"], default="deferred",
                   help="deferred: bài vượt cap (mặc định) · failed: bài fetch lỗi tạm "
                        "thời (timeout/5xx/403) · all: cả hai")
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                   help="số lần thử tối đa trước khi gắn cờ capture_giveup")
    p.add_argument("--retry-window-hours", type=int, default=0,
                   help="chỉ truy đuổi bài có fetched_at trong N giờ gần đây (0 = không giới hạn)")
    p.add_argument("--budget-seconds", type=int, default=0,
                   help="trần thời gian chạy, dừng sạch giữa hai bài (0 = không giới hạn)")
    a = p.parse_args()
    sys.exit(main(a.domain, a.limit, a.fetch, a.dry_run, dates_only=a.dates_only,
                  mode=a.mode, max_attempts=a.max_attempts,
                  retry_window_hours=a.retry_window_hours,
                  budget_seconds=a.budget_seconds))
