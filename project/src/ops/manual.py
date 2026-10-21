"""Register manual waves of `article_run.py` and enforce provider locks and collision checks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from src.core import paths
from src.ops import trace as tracing
from src.ops.config import resolve_paths
from src.ops.lanes import lane_of
from src.ops.store import ACTIVE_WAVE_STATUSES, OpsStore

MODES = ("backlog", "bench", "adhoc")
DAEMON_TRIGGERS = ("T1", "T2", "T3", "retry", "manual-run")
BENCH_ROOT = paths.data_root() / "agent_bench"


class ManualGate:
    """Gate for one manual invocation of `article_run.py`.

    Attributes:
        store: Operations store; None when the daemon issued the call (already registered).
        wave: Wave identifier.
        mode: backlog, bench or adhoc.
        phase: prepare, analyze, repair or finish.
        refusal: Refusal reason; None when the run is allowed.
        runner: Runner chosen on the command line.
        force: True when the human bypassed the collision check and provider lock.
    """

    def __init__(self, store: OpsStore | None, wave: str, mode: str, phase: str,
                 runner: str, force: bool) -> None:
        """Bind the gate to one invocation.

        Args:
            store: Operations store, or None.
            wave: Wave identifier.
            mode: Manual run mode.
            phase: Phase of the invocation.
            runner: Runner chosen on the command line.
            force: True when the human bypasses the collision check and provider lock.
        """
        self.store, self.wave, self.mode, self.phase = store, wave, mode, phase
        self.runner, self.force = runner, force
        self.refusal: str | None = None
        self._root: str | None = None

    @property
    def bench_dir(self) -> Path:
        """Return the dedicated output directory of a bench wave."""
        return BENCH_ROOT / self.wave

    def exclude_ids(self) -> set[str]:
        """List articles reserved by another wave; bench excludes none.

        Returns:
            Set of article identifiers to exclude when packing. Articles that exhausted the
            daemon attempts are still selected, because a manual run is the official path to finish them.
        """
        if self.store is None or self.mode == "bench":
            return set()
        held = self.store.reserved_article_ids()
        with self.store.conn() as c:
            own = {r[0] for r in c.execute(
                "SELECT article_id FROM ops_wave_articles WHERE wave_id = ?", (self.wave,))}
        return held - own

    def finish(self, rc: int, ids: Callable[[], list[str]] | None = None) -> None:
        """Finalize the wave status after the invocation.

        Args:
            rc: Exit code of the invocation.
            ids: Function returning the article list. The prepare phase passes every article
                of the wave to reserve them; the repair phase passes the missing articles to
                count one repair round.
        """
        if self.store is None:
            return
        if self.mode != "bench" and ids is not None:
            if self.phase == "prepare" and rc == 0:
                self.store.record_wave_articles(self.wave, ids())
            elif self.phase == "repair":
                self.store.bump_attempts(ids(), self.wave)
                key = f"repair_rounds:{self.wave}"
                self.store.set_state(key, str(int(self.store.get_state(key, "0") or 0) + 1))
        if self.mode == "bench":
            status, reason = "DONE", f"bench: pha {self.phase}, đầu ra tại {self.bench_dir}"
        elif self.phase == "finish":
            status, reason = ("DONE", "chạy tay: nạp DB xong") if rc == 0 else (
                "FAILED", f"chạy tay: --finish không đạt (rc={rc})")
        else:
            status, reason = "PARKED", f"chạy tay: xong pha {self.phase}, chờ bước kế tiếp"
        self.store.upsert_wave(self.wave, status=status, reason=reason)
        if self._root:
            tracing.Tracer(self.store.path, self.wave).finish(
                self._root, "ok" if rc == 0 else "fail", phase=self.phase, rc=rc)


def begin(wave: str, mode: str | None, phase: str, runner: str, *, force: bool = False,
          target_date: str | None = None) -> ManualGate:
    """Check collisions and the provider lock, then register the manual wave in `ops.db`.

    An invocation issued by the daemon (with `OPS_TRACE_DB` set) is skipped because the
    daemon has already registered it.

    Args:
        wave: Wave identifier.
        mode: backlog, bench, adhoc or None (adhoc).
        phase: prepare, analyze, repair or finish.
        runner: Runner on the command line.
        force: Bypass the collision check and provider lock; an event is recorded.
        target_date: Article date of the wave, if any.

    Returns:
        The ManualGate; a non-None `refusal` means the run is not allowed.
    """
    if os.environ.get(tracing.ENV_DB):
        return ManualGate(None, wave, mode or "adhoc", phase, runner, force)
    paths = resolve_paths()
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
    row = store.wave(wave)
    chosen = mode if mode in MODES else (row["trigger"] if row and row["trigger"] in MODES
                                         else "adhoc")
    gate = ManualGate(store, wave, chosen, phase, runner, force)

    if chosen == "bench" and phase == "finish":
        gate.refusal = "Đợt bench không nạp DB. Xem đầu ra tại " + str(gate.bench_dir)
        return gate
    same_lane = [w for w in store.active_waves(lane_of(chosen)) if w["wave_id"] != wave]
    if not force and same_lane:
        other = same_lane[0]
        gate.refusal = (f"Luồng {chosen} đang chạy đợt {other['wave_id']} ({other['status']}); mỗi luồng "
                        f"tối đa một đợt. Chờ đợt xong hoặc thêm --force (có ghi sự kiện).")
        return gate
    if row and not force and row["trigger"] in DAEMON_TRIGGERS and row["status"] in ACTIVE_WAVE_STATUSES:
        gate.refusal = f"Đợt {wave} do daemon giữ và đang {row['status']}."
        return gate
    if row and phase != "finish" and row["provider"] and row["provider"] != runner:
        if not force:
            gate.refusal = (f"Đợt {wave} đã khoá provider {row['provider']}, lệnh dùng {runner}. "
                            f"Mở đợt mới để thử provider khác (--mode bench), hoặc đổi qua /provider.")
            return gate
        store.emit("provider.override", f"{wave}: {row['provider']} → {runner} (--force)",
                   level="warn", actor="human", wave_id=wave)

    fields = {"trigger": chosen, "provider": row["provider"] if row and row["provider"] else runner}
    if not row:
        fields.update(level="manual", status="ANALYZING", reason=f"chạy tay ({chosen})")
        if target_date:
            fields["target_date"] = target_date
        store.upsert_wave(wave, **fields)
        store.emit("wave.manual_opened", f"{wave}: chạy tay, chế độ {chosen}, runner {runner}",
                   actor="human", wave_id=wave, data={"mode": chosen, "runner": runner})
    store.upsert_wave(wave, status="FINISHING" if phase == "finish" else "ANALYZING")

    tracer = tracing.Tracer(store.path, wave)
    root = f"{wave}.manual.{phase}"
    gate._root = tracer.begin(f"chạy tay {phase}", "workflow", "master-orchestrator", span_id=root,
                              parent_id=None, trigger=chosen, runner=runner, phase=phase)
    os.environ[tracing.ENV_DB] = str(store.path)
    os.environ[tracing.ENV_WAVE] = wave
    if gate._root:
        os.environ[tracing.ENV_PARENT] = gate._root
    return gate
