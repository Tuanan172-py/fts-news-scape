"""Hiển thị bảng điều khiển vận hành trực tiếp trong terminal, mở bằng phím tắt."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stdio import force_utf8_stdio  # noqa: E402
from src.ops.breakers import Breakers  # noqa: E402
from src.ops.config import load_config, resolve_paths  # noqa: E402
from src.ops.reports import log_text, status_text, waves_text  # noqa: E402
from src.ops.store import OpsStore  # noqa: E402

force_utf8_stdio()

COLOR = {"debug": "\x1b[90m", "info": "\x1b[0m", "warn": "\x1b[33m", "error": "\x1b[31m",
         "critical": "\x1b[1;31m"}
RESET = "\x1b[0m"
READ_ONLY = {"/status", "/waves", "/log", "/help"}


def render(store: OpsStore, paths, breakers: Breakers, n_events: int) -> str:
    """Dựng toàn màn hình: trạng thái, đợt gần nhất, dòng sự kiện.

    Args:
        store: Store vận hành.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.
        n_events: Số sự kiện hiển thị.

    Returns:
        Văn bản có mã màu ANSI.
    """
    out = [f"\x1b[1m NEWS-SCAPE OPS · {time.strftime('%H:%M:%S')}  "
           f"(Ctrl+C: gõ lệnh · q: thoát)\x1b[0m", "─" * 100,
           status_text(store, paths, breakers), "─" * 100,
           waves_text(store, 4), "─" * 100]
    for e in store.events(limit=n_events):
        c = COLOR.get(e["level"], "")
        wave = f"[{e['wave_id']}] " if e["wave_id"] else ""
        out.append(f"{c}{e['ts'][11:19]} {e['level'][:4]:4} {e['actor']:8} {wave}"
                   f"{e['kind']}: {e['message'][:140]}{RESET}")
    return "\n".join(out)


def run_command(store: OpsStore, paths, breakers: Breakers, text: str) -> str:
    """Chạy lệnh chỉ đọc tại chỗ, đưa lệnh còn lại vào hộp thư cho daemon.

    Args:
        store: Store vận hành.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.
        text: Lệnh người dùng gõ.

    Returns:
        Kết quả hiển thị.
    """
    text = text.strip()
    if not text.startswith("/"):
        text = "/" + text
    head = text.split()[0]
    if head == "/status":
        return status_text(store, paths, breakers)
    if head == "/waves":
        return waves_text(store, 15)
    if head == "/log":
        parts = text.split()
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 40
        wave = next((p for p in parts[1:] if p.upper().startswith("W")), None)
        return log_text(store, n, wave)
    if head == "/help":
        from src.ops.commands import HELP
        return HELP
    cid = store.enqueue_command(text, actor="console")
    for _ in range(20):
        row = store.command(cid)
        if row and row["status"] != "pending":
            return row["result"]
        time.sleep(0.5)
    return "Daemon chưa xử lý lệnh sau 10 giây (daemon có đang chạy không?)."


def main(argv: list[str] | None = None) -> int:
    """Chạy bảng điều khiển trực tiếp.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    ap = argparse.ArgumentParser(description="Bảng điều khiển vận hành News-Scape")
    ap.add_argument("--events", type=int, default=25, help="Số sự kiện hiển thị")
    ap.add_argument("--refresh", type=float, default=2.0, help="Chu kỳ làm mới (giây)")
    ap.add_argument("--tail", action="store_true", help="Chỉ in sự kiện mới, không vẽ lại màn hình")
    args = ap.parse_args(argv)
    if os.name == "nt":
        os.system("")  # bật xử lý mã ANSI của conhost
    cfg, paths = load_config(), resolve_paths()
    store = OpsStore(paths.ops_db)
    breakers = Breakers(store, cfg["breaker"])
    if args.tail:
        last = 0
        try:
            while True:
                for e in store.events(limit=200, after_id=last):
                    last = e["id"]
                    c = COLOR.get(e["level"], "")
                    print(f"{c}{e['ts'][11:19]} {e['level'][:4]:4} {e['kind']}: "
                          f"{e['message']}{RESET}")
                time.sleep(args.refresh)
        except KeyboardInterrupt:
            return 0
    while True:
        try:
            while True:
                sys.stdout.write("\x1b[2J\x1b[H" + render(store, paths, breakers, args.events) + "\n")
                sys.stdout.flush()
                time.sleep(args.refresh)
        except KeyboardInterrupt:
            pass
        try:
            text = input("\nops> ").strip()
        except (KeyboardInterrupt, EOFError):
            return 0
        if text in ("q", "quit", "exit"):
            return 0
        if text:
            print(run_command(store, paths, breakers, text))
            try:
                input("\n(Enter để quay lại màn hình trực tiếp)")
            except (KeyboardInterrupt, EOFError):
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
