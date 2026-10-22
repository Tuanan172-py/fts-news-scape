"""Interpret operator commands arriving from Telegram or the ops console."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from src.ops.console import reports
from src.ops.runtime.breakers import Breakers
from src.core.ops_config import OpsPaths
from src.ops.runtime.order import FAILOVER_VALUES, LEVELS, MAX_LIMIT_CEILING, PROVIDERS, extend, load_order, save_order
from src.ops.console.present import fmt_date
from src.ops.store import OpsStore

HELP = """Lệnh vận hành

Xem
/status — trạng thái nhanh
/waves [n] — các đợt gần nhất
/log [n] [đợt] — sự kiện gần nhất
/map — trạng thái từng tác nhân
/trace [đợt] — cây vết: tác nhân, skill, script, token
/agent <id> — đặc tả và KPI 7 ngày của một tác nhân
/mandate — tình trạng mandate
/digest — bản tin ngay

Điều khiển đợt
/run — mở đợt ngay
/pause, /resume — ngừng hoặc tiếp tục mở đợt mới
/retry <đợt> — chạy lại đợt tạm dừng hoặc lỗi
/cancel <đợt> — huỷ đợt, nhả bài cho đợt sau
/stop, /unstop — dừng khẩn bằng AGY_STOP, hoặc gỡ cờ
/capture restart — thử lại khởi động morninger

Mandate và provider (cần bấm xác nhận khi nâng quyền)
/level L0|L1 [số bài] — L0 chỉ báo; L1 tự chạy trọn đợt tới nạp DB, trần số bài mỗi đợt
/order extend <ngày> — gia hạn mandate tay (mandate cũng tự gia hạn khi hệ thống khoẻ)
/provider agy|openrouter, /failover never|ask|auto
/reset <provider> — đóng breaker sau khi đã sửa nguyên nhân

Chẩn đoán và cải tiến
/diagnose [đợt] — nhờ ops-sentinel chẩn đoán
/improve — hộp thư cải tiến: Mở story, Hoãn, Bác
/prop open_story|defer|reject <số> — quyết định một đề xuất"""

READ_ONLY = {"/status", "/waves", "/log", "/help", "/start", "/digest", "/map", "/trace",
             "/agent", "/improve", "/mandate"}
CONFIRM = "confirm"
ELEVATING = {"/level", "/order", "/provider", "/failover"}


def _needs_confirm(cmd: str, args: list[str]) -> bool:
    """Report whether a command raises autonomy or changes where article data goes.

    Args:
        cmd: Command name including the leading "/".
        args: Command arguments.

    Returns:
        True when the command requires a second confirmation click.
    """
    if args and args[-1] == CONFIRM:
        return False
    if cmd == "/level":
        return bool(args) and args[0].upper() == "L1"
    if cmd == "/order":
        return True
    if cmd == "/provider":
        return bool(args)
    if cmd == "/failover":
        return bool(args) and args[0] == "auto"
    return False


@dataclass
class Reply:
    """Response to one command.

    Attributes:
        text: Message body.
        buttons: Button rows as [[(label, command)]].
    """

    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)


class Controller(Protocol):
    """Actions the daemon must perform while handling commands.

    Attributes:
        store: Operations store.
        paths: Operations filesystem paths.
        cfg: Operations configuration.
        breakers: Provider circuit breakers.
    """

    store: OpsStore
    paths: OpsPaths
    cfg: dict
    breakers: Breakers

    def request_wave(self) -> str:
        """Request a new wave immediately.

        Returns:
            Message for the operator.
        """
        ...

    def retry_wave(self, wave_id: str) -> str:
        """Re-run a parked or failed wave.

        Args:
            wave_id: Wave identifier.

        Returns:
            Message for the operator.
        """
        ...

    def diagnose_async(self, wave_id: str | None) -> str:
        """Start an asynchronous diagnosis by ops-sentinel.

        Args:
            wave_id: Wave to diagnose, or None for the latest activity.

        Returns:
            Message for the operator.
        """
        ...

    def capture_restart(self) -> str:
        """Retry the startup of the morninger capture.

        Returns:
            Message for the operator.
        """
        ...


_GIT_BASH_PREFIX_RE = re.compile(r"^[A-Za-z]:[/\\]Program Files(?: \(x86\))?[/\\]Git[/\\]")
_PATHLIKE_RE = re.compile(r"^[A-Za-z]:|\\|.+/")


def normalize_command(text: str | None) -> str:
    """Restore a command that Git Bash rewrote into a file path.

    Args:
        text: Raw command string, for example `C:/Program Files/Git/retry W10011100`.

    Returns:
        Command string such as `/retry W10011100`; a non-matching string is returned stripped of whitespace.
    """
    return _GIT_BASH_PREFIX_RE.sub("/", (text or "").strip())


def execute(text: str, ctl: Controller, actor: str = "human") -> Reply:
    """Interpret and execute one command, writing an audit trail.

    Args:
        text: Command such as `/pause` or `/retry W10011100`.
        ctl: Daemon controller.
        actor: Command source (telegram, console).

    Returns:
        Reply to send back to the operator.
    """
    text = normalize_command(text)
    parts = text.split()
    if not parts:
        return Reply(HELP)
    store = ctl.store
    if _PATHLIKE_RE.search(parts[0]):
        store.emit("human.command_rejected", f"{actor}: {text[:120]}", level="warn",
                   actor="human", data={"source": actor})
        return Reply("Lệnh không hợp lệ: chuỗi trông như đường dẫn tệp. Gõ lệnh bắt đầu bằng "
                     "\"/\", ví dụ /retry W10011100. Trên Git Bash hãy chạy bằng PowerShell.")
    # Accept commands without the leading "/" (for example `pause`).
    cmd = "/" + parts[0].split("@")[0].lower().lstrip("/")
    args = parts[1:]
    if cmd not in READ_ONLY:
        store.emit("human.command", f"{actor}: {text.strip()}", actor="human",
                   data={"source": actor})
    try:
        return _dispatch(cmd, args, ctl)
    except Exception as exc:  # noqa: BLE001 — command errors go back to the operator and must not crash the bot
        store.emit("human.command_failed", f"{text.strip()}: {exc}", level="warn",
                   actor="human")
        return Reply(f"Không thực hiện được lệnh {cmd}. Chi tiết đã ghi vào nhật ký, "
                     f"xem bằng /log 5.")


def _mandate_text(paths: OpsPaths) -> str:
    """Describe the current mandate in text for the `/mandate` command.

    Args:
        paths: Operations filesystem paths.

    Returns:
        Operator-facing mandate description.
    """
    from src.ops.console import supervision as sv

    m = sv.mandate_info(paths)
    if not m["exists"]:
        return "Chưa có mandate: daemon ở L0 (chỉ đo và báo). Cấp bằng /level L1."
    left = f"còn {m['days_left']} ngày" if m["days_left"] is not None else "không rõ hạn"
    return (f"Mandate {m['declared']} hiệu lực {m['level']} · hạn {fmt_date(m['valid_until'])} ({left})\n"
            f"Provider {m['provider']} · failover {m['failover']} · tạo bởi {m['created_by'] or '–'}\n"
            f"Tự gia hạn khi hệ thống khoẻ và còn dưới 7 ngày.")


def _dispatch(cmd: str, args: list[str], ctl: Controller) -> Reply:
    store, paths = ctl.store, ctl.paths
    if _needs_confirm(cmd, args):
        full = " ".join([cmd, *args, CONFIRM])
        return Reply(f"Xác nhận: {' '.join([cmd, *args])}?", [[("Xác nhận", full[:64])]])
    if args and args[-1] == CONFIRM and cmd in ELEVATING:
        args = args[:-1]
    if cmd in ("/help", "/start"):
        return Reply(HELP)
    if cmd == "/status":
        return Reply(reports.status_text(store, paths, ctl.breakers),
                     [[("Đợt", "/waves"), ("Nhật ký", "/log"), ("Chạy ngay", "/run")]])
    if cmd == "/waves":
        return Reply(reports.waves_text(store, int(args[0]) if args else 8))
    if cmd == "/log":
        n = int(args[0]) if args and args[0].isdigit() else 15
        wave = next((a for a in args if a.upper().startswith("W")), None)
        return Reply(reports.log_text(store, min(n, 60), wave))
    if cmd == "/digest":
        return Reply(reports.digest_text(store, paths, ctl.breakers))
    if cmd == "/map":
        return Reply(reports.map_text(store, ctl.cfg, paths, ctl.breakers),
                     [[("Cây vết", "/trace"), ("Đề xuất", "/improve")]])
    if cmd == "/trace":
        return Reply(reports.trace_text(store, args[0] if args else None))
    if cmd == "/agent":
        if not args:
            return Reply("Cần mã tác nhân: /agent article-processor")
        return Reply(reports.agent_text(store, args[0]))
    if cmd == "/mandate":
        return Reply(_mandate_text(paths))
    if cmd == "/improve":
        text, buttons = reports.improve_text(store)
        return Reply(text, buttons)
    if cmd == "/prop":
        if len(args) < 2 or not args[1].isdigit():
            return Reply("Dùng: /prop open_story|defer|reject <số>")
        from src.ops.console import improve

        res = improve.decide(store, int(args[1]), args[0], actor="telegram")
        return Reply(res["message"])
    if cmd == "/pause":
        store.set_state("paused", "1")
        return Reply("Đã tạm dừng mở đợt mới. Đợt đang chạy vẫn chạy tiếp.",
                     [[("Tiếp tục", "/resume")]])
    if cmd == "/resume":
        store.set_state("paused", None)
        return Reply("Đã tiếp tục: sensor mở đợt khi đủ điều kiện.")
    if cmd == "/stop":
        if not args or args[0] != "confirm":
            return Reply("Xác nhận dừng khẩn: tạo AGY_STOP và huỷ đợt đang chạy?",
                         [[("Xác nhận dừng", "/stop confirm")]])
        paths.kill_switch.parent.mkdir(parents=True, exist_ok=True)
        paths.kill_switch.write_text("stop từ lệnh vận hành\n", encoding="utf-8")
        waves = store.active_waves()
        for w in waves:
            store.set_state(f"cancel:{w['wave_id']}", "1")
        ids = ", ".join(w["wave_id"] for w in waves)
        return Reply("Đã bật AGY_STOP" + (f" và huỷ {ids}." if waves else ".")
                     + " Gỡ bằng /unstop.")
    if cmd == "/unstop":
        paths.kill_switch.unlink(missing_ok=True)
        return Reply("Đã gỡ AGY_STOP.")
    if cmd == "/run":
        return Reply(ctl.request_wave())
    if cmd == "/retry":
        if not args:
            return Reply("Cần mã đợt: /retry W10011100")
        return Reply(ctl.retry_wave(args[0]))
    if cmd == "/cancel":
        if not args:
            return Reply("Cần mã đợt: /cancel W10011100")
        w = store.wave(args[0])
        if w and w["status"] in ("PARKED", "FAILED"):
            # A stopped wave is cancelled immediately so its articles return to the queue.
            store.upsert_wave(args[0], status="CANCELLED", reason="Người vận hành huỷ.")
            store.emit("wave.cancelled", f"{args[0]}: người vận hành huỷ, nhả bài",
                       actor="human", wave_id=args[0])
            return Reply(f"Đã huỷ {args[0]}; bài của đợt được trả về hàng chờ.")
        store.set_state(f"cancel:{args[0]}", "1")
        return Reply(f"Đã yêu cầu huỷ {args[0]} ở ranh giới bước kế tiếp.")
    if cmd == "/level":
        if not args or args[0].upper() not in LEVELS:
            if args and args[0].upper() in ("L2", "L3"):
                return Reply("Hệ thống đã chuẩn hóa L0/L1 theo ADR-0012 (Amended). "
                             "Vui lòng dùng /level L1 <số bài>")
            return Reply("Dùng: /level L0|L1 [số bài]")
        cap = None
        extra = [a for a in args[1:] if a != CONFIRM]
        if extra:
            if args[0].upper() != "L1" or not extra[0].isdigit()                     or not 1 <= int(extra[0]) <= MAX_LIMIT_CEILING:
                return Reply(f"Số bài phải từ 1 đến {MAX_LIMIT_CEILING}: /level L1 <số bài>")
            cap = int(extra[0])
        order = load_order(paths.standing_order)
        if not order.exists or order.expired():
            order = extend(order, ctl.cfg["autonomy"]["max_order_days"],
                           ctl.cfg["autonomy"]["max_order_days"])
        order.level = args[0].upper()
        if cap is not None:
            order.max_limit = cap
        order.created_by = "human:level"
        save_order(paths.standing_order, order)
        store.set_state("fail_streak", "0")
        tail = f", trần {order.max_limit} bài/đợt" if order.level == "L1" else ""
        return Reply(f"Mức tự chủ: {order.level}{tail}, hiệu lực tới {fmt_date(order.valid_until)}.")
    if cmd == "/order":
        if len(args) < 2 or args[0] != "extend" or not args[1].isdigit():
            return Reply("Dùng: /order extend <số ngày>")
        order = extend(load_order(paths.standing_order), int(args[1]),
                       ctl.cfg["autonomy"]["max_order_days"])
        if order.level == "L0":
            order.level = "L1"
        order.created_by = "human:extend"
        save_order(paths.standing_order, order)
        return Reply(f"Mandate {order.level} gia hạn tới {fmt_date(order.valid_until)}.")
    if cmd == "/provider":
        if not args or args[0] not in PROVIDERS:
            return Reply("Dùng: /provider agy|openrouter")
        order = load_order(paths.standing_order)
        order.provider = args[0]
        order.created_by = "human:provider"
        save_order(paths.standing_order, order)
        return Reply(f"Provider chính: {order.provider}. Đợt mới sẽ dùng provider này.")
    if cmd == "/failover":
        if not args or args[0] not in FAILOVER_VALUES:
            return Reply("Dùng: /failover never|ask|auto")
        order = load_order(paths.standing_order)
        order.failover = args[0]
        order.created_by = "human:failover"
        save_order(paths.standing_order, order)
        return Reply(f"Chính sách chuyển provider: {order.failover}.")
    if cmd == "/reset":
        if not args or args[0] not in PROVIDERS:
            return Reply("Dùng: /reset agy|openrouter")
        ctl.breakers.reset(args[0])
        store.emit("breaker.reset", f"{args[0]}: người vận hành đóng breaker", actor="human")
        return Reply(f"Đã đóng breaker {args[0]}. Đợt PARKED do provider sẽ tự chạy lại.")
    if cmd == "/capture":
        return Reply(ctl.capture_restart())
    if cmd == "/diagnose":
        wave = args[0] if args else None
        return Reply(ctl.diagnose_async(wave))
    return Reply(f"Không hiểu lệnh {cmd}.\n\n{HELP}")
