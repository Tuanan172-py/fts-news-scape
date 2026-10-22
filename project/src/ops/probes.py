"""Measure pipeline health every minute and emit alerts on state transitions."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.ops.order import load_order
from src.ops.present import alert_card
from src.ops.store import OpsStore, now_vn, parse_iso
from src.db.connect import open_ro


@dataclass
class ProbeResult:
    """Result of one health probe.

    Attributes:
        name: Probe name.
        ok: True when healthy.
        severity: Alert level when unhealthy.
        message: Description.
    """

    name: str
    ok: bool
    severity: str
    message: str


def probe_capture(db_path: Path, cfg: dict) -> ProbeResult:
    """Check the freshness of article capture within the monitored hours.

    Args:
        db_path: Path of `monocle.db`.
        cfg: The `probes` section of the configuration.

    Returns:
        The ProbeResult.
    """
    now = now_vn()
    h0, h1 = (cfg.get("capture_hours") or [0, 24])[:2]
    try:
        conn = open_ro(db_path, timeout=10)
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
    """Check that the operations DB is still writable.

    Args:
        db_probe: Write-test function returning (passed, reason).

    Returns:
        The ProbeResult.
    """
    ok, reason = db_probe()
    return ProbeResult("db", ok, "critical", "DB ghi được." if ok else f"DB không ghi được: {reason}")


def probe_disk(data_dir: Path, min_free_gb: float) -> ProbeResult:
    """Check the free space of the data drive.

    Args:
        data_dir: Data directory.
        min_free_gb: Minimum free space threshold in GB.

    Returns:
        The ProbeResult.
    """
    free = shutil.disk_usage(data_dir).free / 1e9
    return ProbeResult("disk", free >= min_free_gb, "error", f"Còn trống {free:.1f} GB.")


def probe_dead_letter(db_path: Path, store: OpsStore, delta_alert: int) -> ProbeResult:
    """Compare the Bronze dead-letter count with the start-of-day baseline.

    Args:
        db_path: Path of `monocle.db`.
        store: Operations store, which holds the start-of-day baseline.
        delta_alert: Increase within the day that triggers an alert.

    Returns:
        The ProbeResult.
    """
    try:
        conn = open_ro(db_path, timeout=10)
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
    """Measure capture coverage against the sitemap (rule 10: missing more than 2% in one day is red).

    Args:
        db_path: Path of `monocle.db`.
        red_pct: Threshold percentage of missing articles.
        days: Number of most recent days to examine.

    Returns:
        The ProbeResult; unhealthy when a (day, source) pair exceeds the missing threshold.
    """
    try:
        conn = open_ro(db_path, timeout=10)
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
    """Check the expiry of the standing order.

    Args:
        order_path: Path of the standing order.

    Returns:
        The ProbeResult.
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
        # The mandate renews itself while healthy; under 3 days left means renewal is blocked.
        return ProbeResult("order", False, "warn",
                           f"Mandate {order.level} còn {hours:.0f} giờ (hạn {order.valid_until}) "
                           f"và chưa được gia hạn.")
    return ProbeResult("order", True, "info", f"{order.level} tới {order.valid_until}.")


def _onedrive_running() -> bool:
    """Report whether the `OneDrive.exe` process is running.

    Returns:
        True when the process is found.
    """
    import psutil

    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == "onedrive.exe":
            return True
    return False


def probe_publish(target: Path | None, cfg: dict,
                  onedrive_running: Callable[[], bool] = _onedrive_running,
                  now: float | None = None) -> ProbeResult:
    """Check the health of the SharePoint publish directory per ADR 0020 section 2.6.

    Four conditions: OneDrive.exe is running; the target is writable (write then delete
    `_manifest/.probe`); no `*-DESKTOP-*` or `*.partial` file is older than 2 hours; and
    `latest.json` is not older than `stale_hours`.

    Args:
        target: Target directory; None when `NEWS_SCAPE_PUBLISH_DIR` is not set.
        cfg: The `publish` section of the configuration.
        onedrive_running: Function that checks the OneDrive process; replaceable in tests.
        now: Epoch seconds; None uses the system time.

    Returns:
        The ProbeResult; unhealthy when at least one condition fails.
    """
    if target is None:
        return ProbeResult("publish", False, "error",
                           "Publisher bật nhưng chưa đặt NEWS_SCAPE_PUBLISH_DIR.")
    now = time.time() if now is None else now
    problems = []
    try:
        if not onedrive_running():
            problems.append("OneDrive.exe không chạy")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"không kiểm được OneDrive.exe ({exc})")
    probe = target / "_manifest" / ".probe"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        problems.append(f"đích không ghi được ({exc})")
    stale = []
    try:
        for p in target.rglob("*"):
            name = p.name
            if ("-DESKTOP-" in name or name.endswith(".partial")) and p.is_file()                     and now - p.stat().st_mtime > 2 * 3600:
                stale.append(p.relative_to(target).as_posix())
    except OSError:
        pass
    if stale:
        problems.append(f"{len(stale)} tệp xung đột hoặc partial cũ, ví dụ {stale[0]}")
    latest = target / "_manifest" / "latest.json"
    limit_h = float(cfg.get("stale_hours", 26))
    if not latest.is_file():
        problems.append("chưa có latest.json")
    else:
        age_h = (now - latest.stat().st_mtime) / 3600
        try:
            updated = parse_iso(json.loads(latest.read_text(encoding="utf-8")).get("updated_at"))
            if updated is not None:
                age_h = (now - updated.timestamp()) / 3600
        except (OSError, ValueError, AttributeError):
            pass
        if age_h > limit_h:
            problems.append(f"latest.json cũ {age_h:.0f} giờ (> {limit_h:.0f})")
    if problems:
        return ProbeResult("publish", False, "error", "Xuất bản: " + "; ".join(problems) + ".")
    return ProbeResult("publish", True, "info", "Thư mục xuất bản khoẻ.")


# Operator action when a probe is abnormal, and the command to inspect further.
PROBE_ACTION = {
    "capture": ("bài mới không được thu thập", "kiểm morninger, thử /capture restart", "/log 15"),
    "db": ("đợt không nạp được bản ghi", "kiểm quyền ghi monocle.db và khoá DB", "/log 15"),
    "disk": ("đợt không đóng gói được", "giải phóng dung lượng ổ dữ liệu", "/status"),
    "dead_letter": ("bài Bronze không vào được Silver", "xem pipeline_radar.py status", "/status"),
    "coverage": ("bài của một số nguồn chưa được thu thập đủ",
                 "chờ cào bù, xem capture_reconcile.py status", "/status"),
    "order": ("daemon sắp về L0 và dừng tự mở đợt", "gia hạn bằng /order extend 30", "/mandate"),
    "publish": ("chuyên viên không thấy dữ liệu mới trên SharePoint",
                "xem docs/operations/publisher.md mục Xử lý sự cố", "/log 15"),
}


def apply_edges(store: OpsStore, results: list[ProbeResult]) -> list[ProbeResult]:
    """Emit alerts when a probe changes between healthy and unhealthy.

    Args:
        store: Operations store.
        results: Probe results.

    Returns:
        The probes that just changed state.
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
