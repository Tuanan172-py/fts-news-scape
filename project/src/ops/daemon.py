"""Chạy control plane khi máy mở: sensor, workflow đợt, heartbeat, probe, supervisor, bot."""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import asdict
from datetime import timedelta

from src.ops import commands, improve, mandate, notify, reports
from src.ops.breakers import Breakers
from src.ops.config import OpsPaths
from src.ops.order import PROVIDERS, load_order
from src.ops.present import alert_card
from src.ops.probes import (apply_edges, probe_capture, probe_db, probe_dead_letter,
                            probe_disk, probe_order)
from src.ops.sensor import decide, read_pending
from src.ops.store import ACTIVE_WAVE_STATUSES, OpsStore, iso, now_vn, parse_iso
from src.ops.supervisor import CaptureSupervisor
from src.ops.wave_flow import WaveSpec, WaveSteps, _default_db_probe


class OpsDaemon:
    """Tiến trình điều phối tất định, không tiêu token, sống liên tục.

    Attributes:
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        secrets: Bí mật (Telegram, healthchecks).
        store: Store vận hành.
        breakers: Breaker theo provider.
        steps: Bộ bước của đợt.
        supervisor: Giám sát tiến trình cào.
    """

    def __init__(self, cfg: dict, paths: OpsPaths, secrets: dict[str, str]) -> None:
        """Dựng daemon, chưa khởi động luồng nào.

        Args:
            cfg: Cấu hình đầy đủ.
            paths: Đường dẫn vận hành.
            secrets: Bí mật.
        """
        self.cfg = cfg
        self.paths = paths
        self.secrets = secrets
        self.store = OpsStore(paths.ops_db, log_dir=paths.log_dir,
                              dedup_minutes=int(cfg["alerts"]["dedup_minutes"]))
        self.breakers = Breakers(self.store, cfg["breaker"])
        self.steps = WaveSteps(self.store, cfg, paths)
        from src.core.config import resolve_db_path
        self.monocle_db = resolve_db_path()
        self.supervisor = CaptureSupervisor(self.store, cfg["supervisor"],
                                            self.monocle_db.parent / "capture.lock",
                                            paths.log_dir / "capture.log")
        token = secrets.get("NEWS_SCAPE_TG_TOKEN")
        self.tg = notify.TelegramClient(token) if token else None
        self.chat_ids = [c.strip() for c in secrets.get("NEWS_SCAPE_TG_CHAT_IDS", "").split(",")
                         if c.strip()]
        self.hc_url = secrets.get("NEWS_SCAPE_HC_URL")
        self.control_room = None
        self.stop_event = threading.Event()
        self._force_wave = threading.Event()
        self._diag_lock = threading.Lock()
        self._wave_lock = threading.Lock()
        self._locks: list = []
        self._dbos_ready = False
        self._last: dict[str, float] = {}

    # ── khởi động ────────────────────────────────────────────────────────────
    def acquire_locks(self) -> bool:
        """Chiếm khoá một thể hiện của daemon và khoá đợt dùng chung với article_tick.

        Returns:
            False khi daemon khác đang chạy.
        """
        from src.core.proclock import SingleInstanceLock

        lock = SingleInstanceLock(self.paths.daemon_lock)
        if not lock.acquire():
            print(f"Daemon khác đang chạy ({lock.holder()}). Thoát.")
            return False
        self._locks.append(lock)
        from scripts.article_tick import PipelineLock

        plock = PipelineLock(self.paths.pipeline_lock)
        while not plock.acquire():
            self.store.emit("daemon.waiting_lock", "Chờ article_tick nhả .pipeline.lock",
                            level="warn")
            if self.stop_event.wait(60):
                return False
        self._locks.append(plock)
        return True

    def start_dbos(self) -> None:
        """Khởi tạo DBOS, gắn bộ bước và khôi phục workflow dang dở."""
        from dbos import DBOS

        from src.ops import dbos_flow

        dbos_flow.init_dbos(self.paths)
        dbos_flow.bind(self.steps, self.cfg)
        DBOS.launch()
        self._dbos_ready = True
        self.reconcile(at_start=True)

    def reconcile(self, *, at_start: bool = False) -> None:
        """Đánh dấu FAILED đợt đang hoạt động mà DBOS không còn chạy workflow của nó.

        Chạy lúc khởi động và ở mỗi nhịp sensor. Workflow kết thúc mà `ops_waves` vẫn ghi
        trạng thái đang chạy (step ném lỗi trước khi kịp chốt) sẽ chặn sensor mãi mãi
        nếu không có lần đối chiếu này.

        Args:
            at_start: True khi gọi lúc daemon vừa khởi động; khi ấy ghi thêm sự kiện
                khôi phục cho đợt còn chạy.
        """
        from dbos import DBOS

        w = self.store.active_wave()
        if not w or not w["workflow_id"]:
            return
        status = DBOS.get_workflow_status(w["workflow_id"])
        if status is None or status.status in ("ERROR", "CANCELLED", "SUCCESS",
                                                "MAX_RECOVERY_ATTEMPTS_EXCEEDED"):
            # Workflow SUCCESS mà hàng đợt chưa chốt chỉ xảy ra khi st_finalize hỏng giữa
            # chừng; coi như FAILED để người xem lại.
            fresh = self.store.wave(w["wave_id"])
            if fresh and fresh["status"] not in ACTIVE_WAVE_STATUSES:
                return
            why = status.status if status else "mất"
            self.store.upsert_wave(w["wave_id"], status="FAILED", finished_at=iso(),
                                   reason=f"Workflow {w['workflow_id']} không còn chạy ({why}).")
            self.store.emit("wave.failed", f"{w['wave_id']}: workflow {why}, đợt kẹt được "
                            f"đánh dấu FAILED", level="error", wave_id=w["wave_id"])
            self.store.alert("error", alert_card(
                "error", f"Đợt {w['wave_id']}: workflow dừng ({why}) khi đang ở {w['status']}",
                "bài của đợt vẫn được giữ chỗ, đợt mới không lấy các bài này",
                "bấm Chạy lại, hoặc Huỷ để nhả bài", f"/log 10 {w['wave_id']}"),
                dedup_key=f"wave:{w['wave_id']}:lost",
                             buttons=[[("Chạy lại", f"/retry {w['wave_id']}"),
                                       ("Huỷ, nhả bài", f"/cancel {w['wave_id']}")]])
        elif at_start:
            self.store.emit("wave.recovered", f"{w['wave_id']}: DBOS chạy tiếp từ bước cuối "
                            f"đã xong", wave_id=w["wave_id"])

    def announce_start(self) -> None:
        """Ghi sự kiện khởi động và cảnh báo khi daemon khởi động lại quá dày."""
        since = iso(now_vn() - timedelta(hours=1))
        with self.store.conn() as c:
            n = c.execute("SELECT COUNT(*) FROM ops_events WHERE kind = 'daemon.started' "
                          "AND ts >= ?", (since,)).fetchone()[0]
        self.store.emit("daemon.started", "ops_daemon khởi động", data={
            "telegram": bool(self.tg and self.chat_ids), "healthchecks": bool(self.hc_url)})
        if n >= 3:
            self.store.alert("critical", alert_card(
                "critical", f"ops_daemon khởi động lại {n + 1} lần trong 1 giờ",
                "đợt đang chạy có thể chậm và lệnh có thể bị mất",
                "tìm nguyên nhân trong ops_logs/daemon.out.log", "/log 20"),
                dedup_key="daemon:flapping")
        else:
            self.store.alert("info", "ops_daemon đã khởi động.", dedup_key="daemon:started")
        if not (self.tg and self.chat_ids):
            self.store.emit("telegram.unconfigured", "Chưa cấu hình Telegram: cảnh báo chỉ "
                            "nằm trong ops.db và console.", level="warn")

    # ── vòng chính ───────────────────────────────────────────────────────────
    def _due(self, name: str, every_s: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, 0.0) >= every_s:
            self._last[name] = now
            return True
        return False

    def run_forever(self) -> int:
        """Chạy daemon đến khi nhận tín hiệu dừng.

        Returns:
            Mã thoát.
        """
        if not self.acquire_locks():
            return 3
        try:
            self.start_dbos()
            self.announce_start()
            self.start_control_room()
            threads = [threading.Thread(target=self._alert_loop, name="alerts", daemon=True),
                       threading.Thread(target=self._sensor_loop, name="sensor", daemon=True)]
            if self.tg and self.chat_ids:
                threads.append(threading.Thread(target=self._telegram_loop, name="telegram",
                                                daemon=True))
            for t in threads:
                t.start()
            while not self.stop_event.is_set():
                self.loop_once()
                self.stop_event.wait(2)
        finally:
            if self.control_room:
                self.control_room.stop()
            self.store.emit("daemon.stopped", "ops_daemon dừng", level="warn")
            notify.drain_alerts(self.store, self.tg, self.chat_ids)
            if self._dbos_ready:
                from dbos import DBOS
                try:
                    DBOS.destroy(destroy_registry=False)
                except Exception:  # noqa: BLE001
                    pass
            for lock in reversed(self._locks):
                lock.release()
        return 0

    def loop_once(self) -> None:
        """Một nhịp của vòng chính; lỗi từng phần được ghi lại, không làm chết daemon."""
        for name, every, fn in (
            ("commands", 2, self.drain_commands),
            ("heartbeat", self.cfg["heartbeat"]["interval_seconds"], self.heartbeat),
            ("supervisor", 15, self.supervise),
            ("probes", 60, self.run_probes),
            ("digest", 30, self.digest_tick),
            ("mandate", 600, self.mandate_tick),
            ("improve", 3600, self.improve_tick),
        ):
            if self._due(name, every):
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    self.store.emit(f"daemon.{name}_error", f"{name}: {exc}", level="error",
                                    data={"trace": traceback.format_exc()[-2000:]})

    def start_control_room(self) -> None:
        """Mở Phòng điều khiển trên 127.0.0.1 nếu cấu hình bật."""
        cr = self.cfg["control_room"]
        if not cr.get("enabled"):
            return
        from src.ops.control_room import ControlRoom

        self.control_room = ControlRoom(self.store, self.cfg, self.paths, self.breakers)
        if not self.control_room.start():
            self.control_room = None

    def mandate_tick(self) -> None:
        """Gia hạn mandate khi sắp hết hạn và hệ thống khoẻ (D-A)."""
        mandate.maybe_renew(self.store, self.cfg, self.paths)

    def improve_tick(self) -> None:
        """Quét vết và KPI để thêm đề xuất cải tiến vào hộp thư (D-E)."""
        improve.sync(self.store, self.cfg)

    def heartbeat(self) -> None:
        """Ghi nhịp tim cục bộ và ping dead-man ngoài máy."""
        self.store.set_state("heartbeat_at", iso())
        w = self.store.active_wave()
        body = f"active={w['wave_id'] if w else '-'} capture={self.supervisor.mode}"
        notify.ping_healthcheck(self.hc_url, "", body)

    def supervise(self) -> None:
        """Giữ tiến trình cào sống."""
        mode = self.supervisor.tick()
        self.store.set_state("capture_mode", mode)

    def run_probes(self) -> None:
        """Đo sức khoẻ và phát cảnh báo theo cạnh."""
        p = self.cfg["probes"]
        results = [probe_capture(self.monocle_db, p)]
        # Thử ghi giành khoá ghi của monocle.db; trong lúc đợt chạy (nhất là lúc nạp DB)
        # phép thử này vừa tranh khoá vừa báo đỏ giả. Preflight của đợt đã thử ghi rồi.
        if not self.store.active_wave():
            results.append(probe_db(_default_db_probe))
        results += [probe_disk(self.paths.data_dir, float(self.cfg["wave"]["min_free_gb"])),
                    probe_dead_letter(self.monocle_db, self.store,
                                      int(p["dead_letter_alert_delta"])),
                    probe_order(self.paths.standing_order)]
        apply_edges(self.store, results)

    def digest_tick(self) -> None:
        """Gửi bản tin vào các mốc giờ cấu hình, mỗi mốc một lần mỗi ngày."""
        now = now_vn()
        for t in self.cfg["digest"]["times"]:
            hh, mm = (int(x) for x in t.split(":"))
            key = f"digest:{now.date().isoformat()}:{t}"
            due = (now.hour, now.minute) >= (hh, mm) and (now.hour * 60 + now.minute) - (hh * 60 + mm) < 30
            if due and not self.store.get_state(key):
                self.store.set_state(key, iso())
                self.store.alert("digest", reports.digest_text(self.store, self.paths,
                                                               self.breakers))

    # ── sensor và đợt ────────────────────────────────────────────────────────
    def _sensor_loop(self) -> None:
        # Bộ chọn bài của article_pack đọc cả nội dung bài nên mất vài giây mỗi lượt;
        # chạy ở luồng riêng để lệnh, nhịp tim và probe không phải chờ.
        interval = float(self.cfg["sensor"]["interval_seconds"])
        while not self.stop_event.is_set():
            try:
                with self._wave_lock:
                    self.sensor_tick()
            except Exception as exc:  # noqa: BLE001
                self.store.emit("daemon.sensor_error", f"sensor: {exc}", level="error",
                                data={"trace": traceback.format_exc()[-2000:]})
            self._force_wave.wait(interval)

    def sensor_tick(self) -> None:
        """Đánh giá điều kiện và mở đợt mới hoặc chạy tiếp đợt chờ provider."""
        force = self._force_wave.is_set()
        self._force_wave.clear()
        if self._dbos_ready:
            self.reconcile()
        if self.store.active_wave():
            # Đang có đợt: không mở đợt mới, nên không đọc lại cả bảng bài trên DB
            # vận hành (bộ chọn bài nặng, và đợt đang chạy cần DB hơn).
            return
        t0 = time.monotonic()
        exclude = self.store.excluded_article_ids(
            int(self.cfg["wave"]["max_attempts_per_article"]))
        reading = read_pending(self.monocle_db, int(self.cfg["sensor"]["lookback_days"]),
                               with_backlog=self._due("backlog", 1800), exclude=exclude)
        fire, rule, reason = decide(reading, self.cfg["sensor"], force=force)
        cached = json.loads(self.store.get_state("sensor:last") or "{}")
        snapshot = {"at": iso(), "per_date": reading.per_date, "total": reading.total,
                    "oldest_age_min": reading.oldest_age_minutes(),
                    "backlog_all": reading.backlog_all if reading.backlog_all is not None
                    else cached.get("backlog_all"), "reason": reason,
                    "excluded": len(exclude), "took_s": round(time.monotonic() - t0, 1)}
        self.store.set_state("sensor:last", json.dumps(snapshot, ensure_ascii=False))

        if self.paths.kill_switch.exists():
            return
        if self.store.get_state("paused") == "1" and not force:
            return
        if not self._dbos_ready:
            return
        order = load_order(self.paths.standing_order)
        level = order.effective_level()
        for w in self.store.parked_for_breaker():
            if level == "L0":
                # Tự chạy lại cũng là tiêu token: không có standing order thì không làm.
                break
            allowed, _ = self.breakers.allow(w["provider"] or "agy")
            if allowed:
                self.store.emit("wave.auto_resume", f"{w['wave_id']}: provider hồi phục, "
                                f"chạy tiếp", wave_id=w["wave_id"])
                self._retry_wave_locked(w["wave_id"])
                return
        if not fire:
            return
        provider = order.provider
        allowed, st = self.breakers.allow(provider)
        if not allowed:
            other = next(p for p in PROVIDERS if p != provider)
            if order.failover == "auto" and self.breakers.allow(other)[0]:
                self.store.emit("provider.failover", f"{provider} OPEN → chuyển {other}",
                                level="warn")
                provider = other
            else:
                if order.failover == "ask":
                    self.store.alert("warn", alert_card(
                        "warn", f"Đủ điều kiện mở đợt nhưng {provider} đang mở ({st.reason})",
                        "đợt mới chưa mở được", f"chuyển sang {other} hoặc chờ breaker tự đóng",
                        "/status"),
                                     dedup_key=f"failover:ask:{provider}",
                                     buttons=[[(f"Dùng {other}", f"/provider {other}"),
                                               ("Chờ", "/status")]])
                return
        if level == "L0" and not force:
            self.store.alert("warn", alert_card(
                "warn", f"Đủ điều kiện mở đợt ({reason}) nhưng chưa có mandate",
                "bài chờ tăng dần, không có đợt nào tự chạy",
                "cấp mandate bằng nút bên dưới, hoặc gõ /level L1", "/status"),
                             dedup_key=f"l0:{now_vn():%Y%m%d%H}",
                             buttons=[[("Cấp mandate L1", "/level L1")]])
            return
        self.open_wave(reading.target_date or now_vn().date().isoformat(),
                       rule, level, provider, order.digest(), reason)

    def open_wave(self, target_date: str, trigger: str, level: str, provider: str,
                  order_hash: str, reason: str) -> str:
        """Ghi hàng đợt và khởi chạy workflow.

        Args:
            target_date: Ngày xuất bản cần xử lý.
            trigger: Luật kích hoạt.
            level: Mức tự chủ áp cho đợt.
            provider: Runner.
            order_hash: Băm standing order.
            reason: Lý do kích hoạt.

        Returns:
            Mã đợt.
        """
        from src.ops import dbos_flow

        base = f"W{now_vn():%m%d%H%M}"
        wave_id, i = base, 0
        while self.store.wave(wave_id) or (self.steps.task_dir / f"wave_{wave_id}.json").exists():
            i += 1
            wave_id = f"{base}{chr(96 + i)}"
        spec = WaveSpec(wave_id, target_date, trigger, level, provider, 0, order_hash)
        self.store.upsert_wave(wave_id, workflow_id=spec.workflow_id, status="SENSED",
                               trigger=trigger, target_date=target_date, level=level,
                               provider=provider, attempt=0)
        msg = f"Mở đợt {wave_id} ({target_date}, {provider}, {level}): {reason}"
        self.store.emit("wave.opened", msg, wave_id=wave_id, data=asdict(spec))
        if self.cfg["alerts"].get("push_wave_info"):
            self.store.alert("info", msg)
        dbos_flow.start_wave(spec)
        return wave_id

    # ── hành động cho lệnh ───────────────────────────────────────────────────
    def request_wave(self) -> str:
        """Yêu cầu sensor mở đợt ngay ở nhịp kế tiếp.

        Returns:
            Phản hồi cho người vận hành.
        """
        if self.store.active_wave():
            return "Đang có đợt chạy; WIP đợt = 1."
        self._force_wave.set()
        return "Đã yêu cầu mở đợt; sensor xử lý trong vài giây."

    def retry_wave(self, wave_id: str) -> str:
        """Chạy lại một đợt từ bước hỏng bằng workflow mới cùng mã đợt.

        Args:
            wave_id: Mã đợt.

        Returns:
            Phản hồi cho người vận hành.
        """
        if self._wave_lock.acquire(timeout=30):
            try:
                return self._retry_wave_locked(wave_id)
            finally:
                self._wave_lock.release()
        return "Sensor đang bận, thử lại sau ít giây."

    def _retry_wave_locked(self, wave_id: str) -> str:
        from src.ops import dbos_flow

        w = self.store.wave(wave_id)
        if not w:
            return f"Không có đợt {wave_id}."
        if w["status"] not in ("PARKED", "FAILED", "CANCELLED"):
            return f"Đợt {wave_id} đang {w['status']}, không chạy lại được."
        active = self.store.active_wave()
        if active:
            return f"Đang có đợt {active['wave_id']} chạy."
        order = load_order(self.paths.standing_order)
        attempt = int(w["attempt"] or 0) + 1
        # Chỉ người gọi được hàm này khi standing order về L0 (sensor không tự chạy lại
        # ở L0), nên chạy lại là một quyết định rõ ràng của người.
        level = "L1"
        spec = WaveSpec(wave_id, w["target_date"], "retry", level,
                        w["provider"] or order.provider, attempt, order.digest())
        self.store.set_state(f"cancel:{wave_id}", None)
        self.store.upsert_wave(wave_id, status="SENSED", attempt=attempt,
                               workflow_id=spec.workflow_id, reason=None, finished_at=None,
                               resume_on_breaker=0)
        self.store.emit("wave.retry", f"{wave_id}: chạy lại lần {attempt}", wave_id=wave_id)
        dbos_flow.start_wave(spec)
        return f"Đã chạy lại {wave_id} (lần {attempt})."

    def diagnose_async(self, wave_id: str | None) -> str:
        """Chạy ops-sentinel ở luồng nền, trả kết quả qua outbox.

        Args:
            wave_id: Đợt cần chẩn đoán.

        Returns:
            Phản hồi tức thì.
        """
        if not self._diag_lock.acquire(blocking=False):
            return "Sentinel đang chẩn đoán một yêu cầu khác."

        def work() -> None:
            from src.ops.sentinel import diagnose

            try:
                d = diagnose(self.store, self.breakers, self.paths.log_dir, wave_id)
                text = (f"Sentinel{' · ' + wave_id if wave_id else ''}: {d.summary}\n"
                        + "".join(f"• {c}\n" for c in d.causes)
                        + f"Đề xuất: {d.command} — {d.rationale}")
                buttons = [[(f"Chạy {d.command}", d.command)]] if d.command != "none" else None
                self.store.alert("info", text, buttons=buttons)
            finally:
                self._diag_lock.release()

        threading.Thread(target=work, name="sentinel", daemon=True).start()
        return "Sentinel đang chẩn đoán; kết quả gửi sau ít phút."

    def capture_restart(self) -> str:
        """Gỡ trạng thái bỏ cuộc của supervisor để thử khởi động lại morninger.

        Returns:
            Phản hồi cho người vận hành.
        """
        self.supervisor.reset()
        return "Supervisor sẽ thử khởi động lại morninger ở nhịp kế tiếp."

    # ── kênh người vận hành ──────────────────────────────────────────────────
    def drain_commands(self) -> None:
        """Xử lý lệnh do ops console đưa vào hộp thư."""
        for row in self.store.pending_commands():
            reply = commands.execute(row["text"], self, actor=row["actor"])
            self.store.finish_command(row["id"], reply.text)

    def _alert_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                notify.drain_alerts(self.store, self.tg, self.chat_ids)
            except Exception as exc:  # noqa: BLE001
                self.store.emit("alerts.error", str(exc), level="warn")
            self.stop_event.wait(3)

    def _telegram_loop(self) -> None:
        offset = int(self.store.get_state("tg_offset", "0") or 0)
        timeout = int(self.cfg["telegram"]["poll_timeout_seconds"])
        while not self.stop_event.is_set():
            try:
                updates = self.tg.get_updates(offset, timeout)
            except Exception as exc:  # noqa: BLE001 — mạng chập chờn: nghỉ rồi thử lại
                self.store.emit("telegram.poll_error", str(exc)[:200], level="debug")
                self.stop_event.wait(15)
                continue
            for up in updates:
                offset = int(up["update_id"]) + 1
                self.store.set_state("tg_offset", str(offset))
                try:
                    self._handle_update(up)
                except Exception as exc:  # noqa: BLE001
                    self.store.emit("telegram.handle_error", str(exc)[:300], level="warn")

    def _authorized(self, chat: dict, sender: dict) -> bool:
        """Chỉ nhận lệnh trong chat riêng, từ đúng người có mã nằm trong danh sách trắng.

        Trong chat riêng, mã chat trùng mã người gửi. Nhóm bị từ chối kể cả khi mã nhóm
        nằm trong danh sách, vì mọi thành viên nhóm đều bấm được nút.

        Args:
            chat: Đối tượng `chat` của Telegram.
            sender: Đối tượng `from` của Telegram.

        Returns:
            True khi được phép.
        """
        chat_id = str(chat.get("id", ""))
        return (chat.get("type") == "private" and chat_id in self.chat_ids
                and str(sender.get("id", "")) == chat_id)

    def _handle_update(self, up: dict) -> None:
        if "callback_query" in up:
            cq = up["callback_query"]
            chat_obj = cq.get("message", {}).get("chat", {})
            chat = str(chat_obj.get("id", ""))
            text = cq.get("data", "")
            if not self._authorized(chat_obj, cq.get("from") or {}):
                self.store.emit("telegram.unauthorized", f"callback từ {chat}", level="warn")
                return
            reply = commands.execute(text, self, actor="telegram")
            self.tg.answer_callback(cq["id"], text)
            self.tg.send(chat, reply.text, buttons=reply.buttons or None)
            return
        msg = up.get("message") or {}
        chat_obj = msg.get("chat", {})
        chat = str(chat_obj.get("id", ""))
        text = msg.get("text", "")
        if not self._authorized(chat_obj, msg.get("from") or {}):
            self.store.emit("telegram.unauthorized", f"tin nhắn từ chat {chat}", level="warn")
            return
        if not text.startswith("/"):
            text = "/help"
        reply = commands.execute(text, self, actor="telegram")
        self.tg.send(chat, reply.text, buttons=reply.buttons or None)


def heartbeat_is_stale(store: OpsStore, max_age_s: float = 180) -> bool:
    """Cho biết nhịp tim daemon đã quá cũ.

    Args:
        store: Store vận hành.
        max_age_s: Ngưỡng số giây.

    Returns:
        True khi chưa có hoặc quá cũ.
    """
    ts = parse_iso(store.get_state("heartbeat_at"))
    return ts is None or (now_vn() - ts).total_seconds() > max_age_s
