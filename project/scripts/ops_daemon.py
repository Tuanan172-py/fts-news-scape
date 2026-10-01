"""Chạy và cấu hình control plane vận hành tự chủ của Article Lane (ADR 0012)."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ops.config import load_config, load_secrets, resolve_paths, write_secret  # noqa: E402


def _redirect_if_windowless(log_dir: Path) -> None:
    """Chuyển stdout/stderr vào tệp khi chạy bằng pythonw (không có console).

    Args:
        log_dir: Thư mục nhật ký.
    """
    if sys.stdout is None or sys.stderr is None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = open(log_dir / "daemon.out.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = fh
        sys.stderr = fh
    else:
        from src.core.stdio import force_utf8_stdio
        force_utf8_stdio()


def cmd_run(_args: argparse.Namespace) -> int:
    """Chạy daemon ở tiền cảnh đến khi nhận tín hiệu dừng.

    Returns:
        Mã thoát.
    """
    cfg, paths = load_config(), resolve_paths()
    _redirect_if_windowless(paths.log_dir)
    from src.ops.daemon import OpsDaemon

    daemon = OpsDaemon(cfg, paths, load_secrets(paths))

    def stop(signum, _frame):
        print(f"Nhận tín hiệu {signum}, dừng daemon...")
        daemon.stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop)
    print(f"ops_daemon chạy · ops.db = {paths.ops_db}")
    return daemon.run_forever()


def cmd_once(_args: argparse.Namespace) -> int:
    """Đo một lượt (sensor, probe) và in kết quả; không mở đợt, không gửi cảnh báo.

    Returns:
        Mã thoát 0.
    """
    from src.core.config import resolve_db_path
    from src.ops.probes import (probe_capture, probe_db, probe_dead_letter, probe_disk,
                                probe_order)
    from src.ops.sensor import decide, read_pending
    from src.ops.store import OpsStore
    from src.ops.wave_flow import _default_db_probe

    cfg, paths = load_config(), resolve_paths()
    db = resolve_db_path()
    store = OpsStore(paths.ops_db)
    t0 = time.monotonic()
    reading = read_pending(db, int(cfg["sensor"]["lookback_days"]), with_backlog=True)
    fire, rule, reason = decide(reading, cfg["sensor"])
    print("=" * 78)
    print(" OPS DAEMON — ĐO MỘT LƯỢT (không mở đợt, không gửi cảnh báo)")
    print("=" * 78)
    print(f"DB vận hành : {db}")
    print(f"Bài chờ     : {reading.total} · " + ", ".join(f"{d}: {n}" for d, n in reading.per_date))
    age = reading.oldest_age_minutes()
    print(f"Lâu nhất    : {age:.0f} phút" if age is not None else "Lâu nhất    : -")
    print(f"Tồn mọi ngày: {reading.backlog_all:,} (ngoài phạm vi tự động)")
    print(f"Sensor      : {'MỞ ĐỢT ' + rule if fire else 'chưa mở'} — {reason}")
    p = cfg["probes"]
    for r in (probe_capture(db, p), probe_db(_default_db_probe),
              probe_disk(paths.data_dir, float(cfg["wave"]["min_free_gb"])),
              probe_dead_letter(db, store, int(p["dead_letter_alert_delta"])),
              probe_order(paths.standing_order)):
        print(f"Probe {r.name:11}: {'KHỎE' if r.ok else 'BẤT THƯỜNG'} · {r.message}")
    secrets = load_secrets(paths)
    print(f"Telegram    : {'đã cấu hình' if secrets.get('NEWS_SCAPE_TG_TOKEN') and secrets.get('NEWS_SCAPE_TG_CHAT_IDS') else 'CHƯA cấu hình'}")
    print(f"Healthchecks: {'đã cấu hình' if secrets.get('NEWS_SCAPE_HC_URL') else 'CHƯA cấu hình'}")
    print(f"Thời gian đo: {time.monotonic() - t0:.1f}s")
    print("=" * 78)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """In trạng thái từ ops.db.

    Returns:
        Mã thoát 0.
    """
    from src.ops.breakers import Breakers
    from src.ops.reports import status_text, waves_text
    from src.ops.store import OpsStore

    cfg, paths = load_config(), resolve_paths()
    store = OpsStore(paths.ops_db)
    print(status_text(store, paths, Breakers(store, cfg["breaker"])))
    print()
    print(waves_text(store))
    cr = cfg["control_room"]
    if cr.get("enabled"):
        print(f"\nPhòng điều khiển: http://127.0.0.1:{cr['port']}  (ops_daemon.py open để mở)")
    return 0


def cmd_open(_args: argparse.Namespace) -> int:
    """Mở Phòng điều khiển trong trình duyệt mặc định.

    Returns:
        Mã thoát 0 khi gửi được lệnh mở, 1 khi Phòng điều khiển đang tắt.
    """
    import webbrowser

    cr = load_config()["control_room"]
    if not cr.get("enabled"):
        print("Phòng điều khiển đang tắt trong config/ops.yaml.")
        return 1
    webbrowser.open(f"http://127.0.0.1:{cr['port']}/")
    return 0


def cmd_order(args: argparse.Namespace) -> int:
    """Tạo hoặc sửa standing order.

    Args:
        args: Tham số dòng lệnh.

    Returns:
        Mã thoát 0.
    """
    from src.ops.order import extend, load_order, save_order

    cfg, paths = load_config(), resolve_paths()
    order = load_order(paths.standing_order)
    if args.level:
        order.level = args.level
    if args.days or not order.exists:
        order = extend(order, args.days or cfg["autonomy"]["max_order_days"],
                       cfg["autonomy"]["max_order_days"])
    if args.provider:
        order.provider = args.provider
    if args.failover:
        order.failover = args.failover
    order.created_by = "human:cli"
    save_order(paths.standing_order, order)
    print(f"Mandate: {order.level} tới {order.valid_until} · provider {order.provider} "
          f"· failover {order.failover} · {paths.standing_order}")
    return 0


def cmd_telegram(args: argparse.Namespace) -> int:
    """Lưu token bot, dò chat id từ tin nhắn đã gửi tới bot và gửi tin thử.

    Args:
        args: Tham số dòng lệnh.

    Returns:
        Mã thoát 0 khi gửi thử thành công.
    """
    from src.ops.notify import TelegramClient

    paths = resolve_paths()
    if args.token:
        write_secret(paths, "NEWS_SCAPE_TG_TOKEN", args.token)
    secrets = load_secrets(paths)
    token = secrets.get("NEWS_SCAPE_TG_TOKEN")
    if not token:
        print("Thiếu token. Tạo bot với @BotFather rồi chạy: ops_daemon.py telegram --token <TOKEN>")
        return 2
    client = TelegramClient(token)
    chats = args.chat_id
    if not chats:
        # Chỉ nhận chat riêng. Daemon từ chối mọi nhóm, và tự đưa mọi chat từng nhắn bot
        # vào danh sách trắng là trao quyền điều khiển cho người lạ.
        updates = client.get_updates(0, timeout=0)
        chats = sorted({str(u["message"]["chat"]["id"]) for u in updates
                        if u.get("message", {}).get("chat", {}).get("type") == "private"})
        if not chats:
            print("Chưa thấy tin nhắn riêng nào. Mở Telegram, nhắn /start cho bot trong chat "
                  "riêng rồi chạy lại lệnh này.")
            return 2
        if len(chats) > 1:
            print(f"Thấy {len(chats)} chat riêng: {', '.join(chats)}. Chỉ định rõ người nhận "
                  f"bằng --chat-id <mã>.")
            return 2
    write_secret(paths, "NEWS_SCAPE_TG_CHAT_IDS", ",".join(chats))
    for c in chats:
        client.send(c, "[THÔNG TIN] News-Scape: đã kết nối Telegram. Gõ /help để xem lệnh.")
    print(f"Đã lưu chat id {', '.join(chats)} vào {paths.secrets_file} và gửi tin thử.")
    return 0


def cmd_healthcheck(args: argparse.Namespace) -> int:
    """Lưu URL ping dead-man và ping thử.

    Args:
        args: Tham số dòng lệnh.

    Returns:
        Mã thoát 0 khi ping thành công.
    """
    from src.ops.notify import ping_healthcheck

    paths = resolve_paths()
    write_secret(paths, "NEWS_SCAPE_HC_URL", args.url)
    ok = ping_healthcheck(args.url, "", "ops_daemon setup")
    print(f"Đã lưu URL. Ping thử: {'thành công' if ok else 'THẤT BẠI'}.")
    return 0 if ok else 1


def cmd_watchdog(_args: argparse.Namespace) -> int:
    """Báo khi daemon chết trong lúc máy đang mở; Task Scheduler gọi lệnh này mỗi 5 phút.

    Máy ngủ thì lệnh này cũng không chạy, nên không có báo động giả khi gập máy. Ngay
    sau khi máy thức, nhịp tim có thể còn cũ vài phút trong lúc daemon chưa kịp ghi; vì
    vậy chỉ báo khi nhịp tim cũ ở **hai lần kiểm liên tiếp**.

    Returns:
        Mã thoát 0.
    """
    from src.ops.notify import TelegramClient, ping_healthcheck
    from src.ops.present import alert_card
    from src.ops.store import OpsStore, iso, now_vn, parse_iso

    cfg, paths = load_config(), resolve_paths()
    _redirect_if_windowless(paths.log_dir)
    store = OpsStore(paths.ops_db)
    stale_min = float(cfg["watchdog"]["stale_minutes"])
    beat = parse_iso(store.get_state("heartbeat_at"))
    age = (now_vn() - beat).total_seconds() / 60 if beat else None
    if age is not None and age <= stale_min:
        store.set_state("watchdog:stale_seen", None)
        store.set_state("watchdog:alerted", None)
        return 0
    if not store.get_state("watchdog:stale_seen"):
        store.set_state("watchdog:stale_seen", iso())
        return 0
    if store.get_state("watchdog:alerted"):
        return 0
    store.set_state("watchdog:alerted", iso())
    since = (f"{age:.0f} phút" if age is not None else "chưa từng ghi")
    text = alert_card("critical", f"ops_daemon không còn nhịp tim ({since})",
                      "đợt mới không được mở và bài chờ không được xử lý, máy vẫn đang mở",
                      "chạy Start-ScheduledTask news-scape-ops",
                      "ops_logs/daemon.out.log")
    store.emit("watchdog.daemon_dead", text, level="critical", actor="daemon")
    secrets = load_secrets(paths)
    token = secrets.get("NEWS_SCAPE_TG_TOKEN")
    chats = [c.strip() for c in secrets.get("NEWS_SCAPE_TG_CHAT_IDS", "").split(",") if c.strip()]
    if token and chats:
        client = TelegramClient(token)
        for c in chats:
            try:
                client.send(c, text)
            except Exception as exc:  # noqa: BLE001 — mạng lỗi: sự kiện đã ghi trong ops.db
                store.emit("watchdog.send_failed", str(exc), level="warn")
    ping_healthcheck(secrets.get("NEWS_SCAPE_HC_URL"), "/fail", text)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    """Đưa một lệnh vào hộp thư cho daemon đang chạy và chờ kết quả.

    Args:
        args: Tham số dòng lệnh.

    Returns:
        Mã thoát 0 khi daemon xử lý trong thời hạn.
    """
    from src.ops.store import OpsStore

    paths = resolve_paths()
    store = OpsStore(paths.ops_db)
    cid = store.enqueue_command(" ".join(args.text), actor="cli")
    for _ in range(30):
        row = store.command(cid)
        if row and row["status"] != "pending":
            print(row["result"])
            return 0
        time.sleep(1)
    print("Daemon chưa xử lý lệnh sau 30 giây (daemon có đang chạy không?).")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Giao diện dòng lệnh của ops_daemon.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    if sys.stdout is not None:
        from src.core.stdio import force_utf8_stdio
        force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Control plane vận hành tự chủ (ADR 0012)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="Chạy daemon (Task Scheduler gọi lệnh này)")
    sub.add_parser("once", help="Đo một lượt, không mở đợt")
    sub.add_parser("status", help="In trạng thái từ ops.db")
    sub.add_parser("watchdog", help="Báo khi daemon chết lúc máy mở (Task Scheduler gọi)")
    sub.add_parser("open", help="Mở Phòng điều khiển trong trình duyệt")
    o = sub.add_parser("order", help="Tạo hoặc sửa mandate")
    o.add_argument("--level", choices=["L0", "L1"])
    o.add_argument("--days", type=int)
    o.add_argument("--provider", choices=["agy", "openrouter"])
    o.add_argument("--failover", choices=["never", "ask", "auto"])
    t = sub.add_parser("telegram", help="Cấu hình bot Telegram")
    t.add_argument("--token")
    t.add_argument("--chat-id", action="append")
    h = sub.add_parser("healthcheck", help="Cấu hình dead-man healthchecks.io")
    h.add_argument("--url", required=True)
    s = sub.add_parser("send", help="Gửi lệnh cho daemon đang chạy, ví dụ: send /status")
    s.add_argument("text", nargs="+")
    args = ap.parse_args(argv)
    return {"run": cmd_run, "once": cmd_once, "status": cmd_status, "order": cmd_order,
            "telegram": cmd_telegram, "healthcheck": cmd_healthcheck,
            "watchdog": cmd_watchdog, "open": cmd_open, "send": cmd_send}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
