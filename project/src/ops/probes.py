"""Đo sức khoẻ pipeline mỗi phút và phát cảnh báo theo cạnh chuyển trạng thái."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.ops.order import load_order
from src.ops.present import alert_card
from src.ops.store import OpsStore, now_vn, parse_iso


@dataclass
class ProbeResult:
    """Kết quả một phép đo sức khoẻ.

    Attributes:
        name: Tên phép đo.
        ok: True khi khoẻ.
        severity: Mức cảnh báo khi không khoẻ.
        message: Mô tả.
    """

    name: str
    ok: bool
    severity: str
    message: str


def probe_capture(db_path: Path, cfg: dict) -> ProbeResult:
    """Kiểm độ tươi của cào tin trong khung giờ theo dõi.

    Args:
        db_path: Đường dẫn `monocle.db`.
        cfg: Mục `probes` của cấu hình.

    Returns:
        ProbeResult.
    """
    now = now_vn()
    h0, h1 = (cfg.get("capture_hours") or [0, 24])[:2]
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            row = conn.execute("SELECT MAX(fetched_at) FROM articles").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return ProbeResult("capture", False, "error", f"Không đọc được DB: {exc}")
    last = parse_iso(row[0]) if row else None
    if last is None:
        return ProbeResult("capture", False, "error", "Chưa có bài nào được cào.")
    age = (now - last).total_seconds() / 60
    limit = float(cfg.get("capture_stale_minutes", 30))
    if age > limit and h0 <= now.hour < h1:
        return ProbeResult("capture", False, "error",
                           f"Cào tin đứng {age:.0f} phút (> {limit:.0f}). Bài mới nhất {row[0]}.")
    return ProbeResult("capture", True, "info", f"Bài mới nhất cách {age:.0f} phút.")


def probe_db(db_probe: Callable[[], tuple[bool, str]]) -> ProbeResult:
    """Kiểm DB vận hành còn ghi được.

    Args:
        db_probe: Hàm thử ghi, trả (đạt, lý do).

    Returns:
        ProbeResult.
    """
    ok, reason = db_probe()
    return ProbeResult("db", ok, "critical", "DB ghi được." if ok else f"DB không ghi được: {reason}")


def probe_disk(data_dir: Path, min_free_gb: float) -> ProbeResult:
    """Kiểm dung lượng trống của ổ dữ liệu.

    Args:
        data_dir: Thư mục dữ liệu.
        min_free_gb: Ngưỡng tối thiểu.

    Returns:
        ProbeResult.
    """
    free = shutil.disk_usage(data_dir).free / 1e9
    return ProbeResult("disk", free >= min_free_gb, "error", f"Còn trống {free:.1f} GB.")


def probe_dead_letter(db_path: Path, store: OpsStore, delta_alert: int) -> ProbeResult:
    """So số Bronze dead-letter với mốc đầu ngày.

    Args:
        db_path: Đường dẫn `monocle.db`.
        store: Store vận hành, giữ mốc đầu ngày.
        delta_alert: Mức tăng trong ngày thì cảnh báo.

    Returns:
        ProbeResult.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            n = conn.execute("SELECT COUNT(*) FROM silver_failures WHERE dead_letter = 1"
                             ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return ProbeResult("dead_letter", True, "info", "Chưa có bảng silver_failures.")
    key = f"dead_letter_base:{now_vn().date().isoformat()}"
    base = store.get_state(key)
    if base is None:
        store.set_state(key, str(n))
        base = str(n)
    delta = n - int(base)
    ok = delta < delta_alert
    return ProbeResult("dead_letter", ok, "error",
                       f"Bronze dead-letter {n:,} (tăng {delta} trong ngày). "
                       f"Xem: pipeline_radar.py status.")


def probe_coverage(db_path: Path, red_pct: float = 2.0, days: int = 2) -> ProbeResult:
    """Đo độ phủ thu thập so với sitemap (rule 10: thiếu quá 2% trong một ngày là đỏ).

    Args:
        db_path: Đường dẫn `monocle.db`.
        red_pct: Ngưỡng phần trăm bài thiếu.
        days: Số ngày gần nhất xét.

    Returns:
        ProbeResult; không khoẻ khi có cặp (ngày, nguồn) thiếu quá ngưỡng.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            rows = conn.execute(
                "SELECT source_domain, SUM(ref_n), SUM(missing_n) FROM capture_coverage "
                "WHERE day >= date('now', ?, 'localtime') GROUP BY source_domain",
                (f"-{days - 1} days",)).fetchall()
            pending = conn.execute("SELECT COUNT(*) FROM discovered_urls "
                                   "WHERE state = 'discovered'").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return ProbeResult("coverage", True, "info", "Chưa có bảng độ phủ thu thập.")
    bad = [(d, 100.0 * m / r) for d, r, m in rows if r and 100.0 * m / r > red_pct]
    if not bad:
        return ProbeResult("coverage", True, "warn", f"Độ phủ đạt, {pending:,} URL chờ cào bù.")
    worst = ", ".join(f"{d} thiếu {pct:.0f}%" for d, pct in sorted(bad, key=lambda x: -x[1])[:3])
    return ProbeResult("coverage", False, "warn",
                       f"Thu thập thiếu so với sitemap: {worst}; {pending:,} URL chờ cào bù.")


def probe_order(order_path: Path) -> ProbeResult:
    """Kiểm hạn của standing order.

    Args:
        order_path: Đường dẫn standing order.

    Returns:
        ProbeResult.
    """
    order = load_order(order_path)
    if not order.exists:
        return ProbeResult("order", False, "warn",
                           "Chưa có mandate: daemon ở L0, chỉ báo khi đủ ngưỡng.")
    hours = order.hours_left()
    if hours <= 0:
        return ProbeResult("order", False, "warn",
                           f"Mandate hết hạn ({order.valid_until}): daemon về L0.")
    if hours <= 72:
        # Mandate tự gia hạn khi khoẻ; còn dưới 3 ngày nghĩa là việc gia hạn đang bị chặn.
        return ProbeResult("order", False, "warn",
                           f"Mandate {order.level} còn {hours:.0f} giờ (hạn {order.valid_until}) "
                           f"và chưa được gia hạn.")
    return ProbeResult("order", True, "info", f"{order.level} tới {order.valid_until}.")


# Việc người vận hành cần làm khi một phép đo bất thường, và lệnh để xem thêm.
PROBE_ACTION = {
    "capture": ("bài mới không được thu thập", "kiểm morninger, thử /capture restart", "/log 15"),
    "db": ("đợt không nạp được bản ghi", "kiểm quyền ghi monocle.db và khoá DB", "/log 15"),
    "disk": ("đợt không đóng gói được", "giải phóng dung lượng ổ dữ liệu", "/status"),
    "dead_letter": ("bài Bronze không vào được Silver", "xem pipeline_radar.py status", "/status"),
    "coverage": ("bài của một số nguồn chưa được thu thập đủ",
                 "chờ cào bù, xem capture_reconcile.py status", "/status"),
    "order": ("daemon sắp về L0 và dừng tự mở đợt", "gia hạn bằng /order extend 30", "/mandate"),
}


def apply_edges(store: OpsStore, results: list[ProbeResult]) -> list[ProbeResult]:
    """Phát cảnh báo khi một phép đo đổi trạng thái khoẻ ↔ không khoẻ.

    Args:
        store: Store vận hành.
        results: Kết quả các phép đo.

    Returns:
        Các phép đo vừa đổi trạng thái.
    """
    changed = []
    for r in results:
        key = f"probe:{r.name}"
        prev = store.get_state(key)
        cur = "ok" if r.ok else "bad"
        if prev == cur:
            continue
        store.set_state(key, cur)
        if prev is None and r.ok:
            continue
        changed.append(r)
        if r.ok:
            store.emit(f"probe.{r.name}.recovered", r.message, actor="daemon")
            store.alert("info", f"Phép đo {r.name} đã hồi phục: {r.message}",
                        dedup_key=f"probe:{r.name}:ok")
        else:
            store.emit(f"probe.{r.name}.failed", r.message, level=r.severity
                       if r.severity in ("warn", "error", "critical") else "warn",
                       actor="daemon")
            impact, action, view = PROBE_ACTION.get(
                r.name, ("chưa rõ", "xem nhật ký", "/log 15"))
            store.alert(r.severity, alert_card(
                r.severity if r.severity in ("critical", "error", "warn") else "warn",
                f"Phép đo {r.name} bất thường: {r.message}", impact, action, view),
                dedup_key=f"probe:{r.name}:bad")
    return changed
