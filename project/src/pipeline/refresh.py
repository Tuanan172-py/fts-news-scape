"""Tải lại các bài viết trong danh sách theo dõi để kích hoạt phát hiện thay đổi.

Cung cấp cơ chế re-fetch có kiểm soát các URL đã biết từ trước để tạo bản capture
thứ hai tầng Bronze, từ đó cho phép bộ phát hiện thay đổi (Change Detection) so sánh.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from src.core.models import now_vn_iso
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate
from src.pipeline.run import process_meta


def select_watchlist(store, *, limit: int = 50, domains: list[str] | None = None) -> list[dict]:
    """Lấy danh sách các bài viết mới nhất cần kiểm tra thay đổi nội dung.

    Args:
        store: Đối tượng ArticleStore kết nối cơ sở dữ liệu.
        limit: Số lượng bài viết tối đa cần lấy.
        domains: Danh sách tên miền cần lọc (tùy chọn).

    Returns:
        Danh sách từ điển chứa thông tin URL, mã băm và tên miền nguồn.
    """
    conn = store.connect()
    try:
        sql = "SELECT url, url_title_hash, source_domain FROM articles"
        params: list = []
        if domains:
            sql += " WHERE source_domain IN (%s)" % ",".join("?" for _ in domains)
            params += list(domains)
        sql += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _meta_path_of(cap: dict) -> str:
    """Xác định đường dẫn tệp .meta.json tương ứng từ kết quả capture."""
    hp = cap.get("html_path", "")
    return hp[:-5] + ".meta.json" if hp.endswith(".html") else ""


def refresh_row(http, raw_store: RawStore, robots: RobotsGate | None, row: dict,
                *, timeout: int = 30, fetched_at: str | None = None) -> dict:
    """Tải lại nội dung của một bài viết và lưu bản capture mới vào tầng Bronze.

    Args:
        http: Đối tượng HTTP client gửi yêu cầu tải trang.
        raw_store: Đối tượng RawStore quản lý lưu trữ tệp thô.
        robots: Cổng kiểm tra quyền truy cập robots.txt.
        row: Dữ liệu bản ghi bài viết cần tải lại.
        timeout: Thời gian chờ HTTP tối đa tính bằng giây.
        fetched_at: Mốc thời gian thu thập bài viết theo chuẩn ISO.

    Returns:
        Từ điển chứa URL, trạng thái thu thập và đường dẫn tệp siêu dữ liệu mới.
    """
    url = row["url"]
    if robots is not None and not robots.allowed(url):
        return {"url": url, "capture_status": "skipped_robots", "meta_path": ""}
    fetched_at = fetched_at or now_vn_iso()
    html_path, meta_path = raw_store.paths_for(row["source_domain"],
                                               row["url_title_hash"], fetched_at)
    if os.path.exists(html_path):
        return {"url": url, "capture_status": "skipped_exists",
                "meta_path": meta_path if os.path.exists(meta_path) else ""}
    if hasattr(http, "rate_limiter"):
        http.rate_limiter.wait(url)
    resp = http.get_response(url, timeout=timeout)
    cap = raw_store.save(row["source_domain"], url, row["url_title_hash"], resp,
                         fetched_at=fetched_at)
    return {"url": url, "capture_status": cap["capture_status"],
            "meta_path": _meta_path_of(cap)}


def refresh_watchlist(store, http, *, limit: int = 50, domains: list[str] | None = None,
                      respect_robots: bool = True, raw_dir: str = "data/raw_html",
                      timeout: int = 30, do_process: bool = True,
                      silver_dir: str = "data/silver",
                      package_dir: str = "data/work_packages") -> dict:
    """Tải lại danh sách theo dõi và kích hoạt chuỗi xử lý tinh chế phát hiện thay đổi.

    Args:
        store: Đối tượng ArticleStore quản lý cơ sở dữ liệu.
        http: Đối tượng HTTP client gửi yêu cầu tải trang.
        limit: Số lượng bài viết tối đa cần quét lại.
        domains: Danh sách tên miền cần lọc.
        respect_robots: Cờ tuân thủ quy tắc tệp robots.txt.
        raw_dir: Thư mục chứa dữ liệu thô Bronze.
        timeout: Thời gian chờ yêu cầu mạng tính bằng giây.
        do_process: Cờ cho phép xử lý tiếp sang tầng Silver và phân loại.
        silver_dir: Thư mục lưu trữ kết quả tầng Silver.
        package_dir: Thư mục lưu trữ gói công việc bàn giao.

    Returns:
        Từ điển tóm tắt kết quả tải lại và thống kê các trạng thái phát hiện.
    """
    raw_store = RawStore(raw_dir)
    robots = RobotsGate(http) if respect_robots else None
    rows = select_watchlist(store, limit=limit, domains=domains)
    summary = {"selected": len(rows), "refetched": 0, "skipped": 0, "states": {}}
    for row in rows:
        # Fix B: 1 URL lỗi (HTTP/parse) KHÔNG được làm sập cả watch-list.
        try:
            res = refresh_row(http, raw_store, robots, row, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — non-fatal per URL
            logger.error("[refresh] fetch fail {}: {}", row.get("url"), e)
            summary["skipped"] += 1
            continue
        if res["capture_status"] not in ("ok", "partial"):
            summary["skipped"] += 1
            continue
        summary["refetched"] += 1
        if do_process and res["meta_path"] and Path(res["meta_path"]).exists():
            try:
                out = process_meta(store, res["meta_path"], silver_dir=silver_dir,
                                   package_dir=package_dir)
                st = out.get("state", "?")
                summary["states"][st] = summary["states"].get(st, 0) + 1
            except Exception as e:  # noqa: BLE001 — non-fatal per bài
                logger.error("refresh process fail {}: {}", res["meta_path"], e)
    logger.info("refresh done: {}", summary)
    return summary
