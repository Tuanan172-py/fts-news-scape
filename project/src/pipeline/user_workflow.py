"""Quy trình điều phối toàn trình dữ liệu phân phối cho người dùng cuối.

Kết nối các bước biên dịch danh mục đăng ký, nạp kết quả thẩm định từ Agent
và xuất bản tệp tin bàn giao cá nhân hóa theo từng người dùng.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.users.compile import (
    DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT_ROOT, compile_all, enabled_users,
)


def union_subscription(registry, users) -> set[str]:
    """Hợp nhất toàn bộ các thực thể mà tập người dùng chỉ định đã đăng ký theo dõi.

    Args:
        registry: Đối tượng EntityRegistry quản lý danh mục thực thể.
        users: Danh sách tên người dùng.

    Returns:
        Tập hợp các mã thực thể duy nhất.
    """
    ids: set[str] = set()
    for u in users:
        ids |= registry.resolve_subscription(u)
    return ids


def _ingest_dir(runner_ingest, outputs_dir: str | Path) -> tuple[int, int]:
    """Nạp toàn bộ các tệp kết quả JSON trong thư mục chỉ định qua hàm ingest."""
    ok = fail = 0
    for p in sorted(Path(outputs_dir).glob("*.json")):
        try:
            res = runner_ingest(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("ingest fail {}: {}", p.name, e)
            fail += 1
            continue
        ok += 1 if res.get("dod_pass") or res.get("cached") else 0
        fail += 0 if res.get("dod_pass") or res.get("cached") else 1
    return ok, fail


def run(*, input_root: str | Path = DEFAULT_INPUT_ROOT,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        store=None, registry=None, db_path: str | None = None,
        users: list[str] | None = None, date: str | None = None, days: int | None = None,
        do_compile: bool = True,
        force: bool = False,
        l1_outputs_dir: str | Path | None = None,
        agent_outputs_dir: str | Path | None = None) -> dict:
    """Thực thi luồng công việc biên dịch đăng ký, nạp kết quả và xuất bản tin cho người dùng.

    Args:
        input_root: Thư mục chứa tệp đăng ký người dùng.
        output_root: Thư mục lưu kết quả bàn giao.
        store: Đối tượng ArticleStore kết nối cơ sở dữ liệu.
        registry: Đối tượng EntityRegistry ánh xạ thực thể.
        db_path: Đường dẫn tệp tin cơ sở dữ liệu (nếu store là None).
        users: Danh sách người dùng cần xử lý (None để lấy toàn bộ người dùng kích hoạt).
        date: Lọc theo ngày xuất bản cụ thể ('YYYY-MM-DD').
        days: Lọc theo số ngày gần nhất.
        do_compile: Cờ cho phép biên dịch lại tệp Excel/CSV đăng ký.
        force: Cờ ghi đè tệp tin kết quả xuất bản dù đã tồn tại.
        l1_outputs_dir: Thư mục chứa kết quả nạp thẩm định L1 (tùy chọn).
        agent_outputs_dir: Thư mục chứa kết quả nạp phân tích Gold (tùy chọn).

    Returns:
        Từ điển thống kê danh sách người dùng kích hoạt, số dòng xuất bản và tổng số.
    """
    from src.agent.entities import load_registry

    # 1. compile input → yaml, rồi reload subscription từ disk
    if do_compile:
        compile_all(input_root, registry or load_registry())
        reg = load_registry()
    else:
        reg = registry or load_registry()

    # 2. tập user BẬT
    enabled = {u.strip() for u in users if u.strip()} if users else enabled_users(input_root)

    # 3. store
    if store is None:
        from src.core.config import load_settings
        from src.db.store import ArticleStore
        store = ArticleStore(db_path=db_path or load_settings().get("database", {}).get("path", "data/monocle.db"))

    # 4. ingest output đã nộp (nếu có) — idempotent (DB trả cached khi đã đạt)
    if l1_outputs_dir:
        from src.agent.l1_runner import L1Runner
        r = L1Runner(store, reg)
        ok, fail = _ingest_dir(r.ingest_output, l1_outputs_dir)
        logger.info("L1 ingest: ok={} fail={}", ok, fail)
    if agent_outputs_dir:
        from src.agent.runner import AgentRunner
        a = AgentRunner(store)
        ok, fail = _ingest_dir(a.ingest_output, agent_outputs_dir)
        logger.info("agent ingest: ok={} fail={}", ok, fail)

    # 5. output cuối per user (gate tối thiểu L1, Gold là enrichment tùy chọn + checkpoint)
    from src.export.user_output import UserOutputWriter
    # enabled là input-driven & authoritative: tập rỗng = KHÔNG user nào (đừng đổi thành None=all).
    writer = UserOutputWriter(store, reg, output_root=output_root, enabled=enabled)
    counts = writer.write(date=date, days=days, force=force)
    total = sum(counts.values())
    logger.info("done workflow: enabled={} users_with_output={} total_rows={}",
                sorted(enabled), len(counts), total)
    return {"enabled": sorted(enabled), "counts": counts, "total": total}
