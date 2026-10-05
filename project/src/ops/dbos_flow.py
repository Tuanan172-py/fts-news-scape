"""Bọc vòng đời đợt thành workflow DBOS bền, mỗi bước là một step có checkpoint."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dbos import DBOS, SetWorkflowID

from src.ops.config import OpsPaths
from src.ops.wave_flow import DirectOps, WaveSpec, WaveSteps, drive_wave

# Ghim phiên bản ứng dụng: DBOS chỉ khôi phục workflow cùng phiên bản, mặc định phiên
# bản băm từ mã nguồn nên sửa mã giữa chừng sẽ bỏ rơi đợt dang dở. Chỉ tăng số này khi
# đổi thứ tự hoặc số lượng step của `drive_wave`.
APP_VERSION = "ops-v2"

_runtime: dict[str, Any] = {}


def init_dbos(paths: OpsPaths) -> None:
    """Khởi tạo DBOS với DB hệ thống SQLite riêng ngoài OneDrive.

    Args:
        paths: Đường dẫn vận hành.
    """
    url = "sqlite:///" + str(paths.dbos_db).replace("\\", "/")
    DBOS(config={"name": "news-scape-ops", "system_database_url": url,
                 "application_version": APP_VERSION, "log_level": "WARNING"})


def bind(steps: WaveSteps, cfg: dict) -> None:
    """Gắn bộ bước và cấu hình cho các step DBOS.

    Args:
        steps: WaveSteps của daemon.
        cfg: Cấu hình đầy đủ.
    """
    _runtime["direct"] = DirectOps(steps)
    _runtime["cfg"] = cfg


def _direct() -> DirectOps:
    return _runtime["direct"]


@DBOS.step()
def st_preflight(spec: dict) -> list:
    """Step bền: preflight."""
    return _direct().preflight(spec)


@DBOS.step()
def st_prepare(spec: dict) -> int:
    """Step bền: đóng gói."""
    return _direct().prepare(spec)


@DBOS.step()
def st_analyze(spec: dict, round_no: int) -> dict:
    """Step bền: phân tích hoặc vá."""
    return _direct().analyze(spec, round_no)


@DBOS.step()
def st_stop_requested(spec: dict) -> bool:
    """Step bền: đọc cờ dừng ở ranh giới trước bước nạp DB."""
    return _direct().stop_requested(spec)


@DBOS.step()
def st_finish(spec: dict) -> list:
    """Step bền: hoàn tất và nạp DB."""
    return _direct().finish(spec)


@DBOS.step()
def st_finalize(spec: dict, status: str, reason: str, flags: dict) -> str:
    """Step bền: chốt trạng thái cuối."""
    return _direct().finalize(spec, status, reason, flags)


class DbosOps:
    """Bộ bước của `drive_wave` đi qua step DBOS."""

    def preflight(self, spec: dict) -> list:
        return st_preflight(spec)

    def prepare(self, spec: dict) -> int:
        return st_prepare(spec)

    def analyze(self, spec: dict, round_no: int) -> dict:
        return st_analyze(spec, round_no)

    def stop_requested(self, spec: dict) -> bool:
        return st_stop_requested(spec)

    def finish(self, spec: dict) -> list:
        return st_finish(spec)

    def finalize(self, spec: dict, status: str, reason: str, flags: dict) -> str:
        return st_finalize(spec, status, reason, flags)


@DBOS.workflow()
def wave_workflow(spec: dict) -> str:
    """Workflow bền của một đợt.

    Args:
        spec: WaveSpec dạng từ điển.

    Returns:
        Trạng thái cuối.
    """
    try:
        return drive_wave(spec, DbosOps(), _runtime["cfg"])
    except Exception as exc:  # noqa: BLE001 — step ném lỗi thì đợt phải về FAILED, không kẹt
        return st_finalize(spec, "FAILED", f"Bước của đợt ném lỗi: {exc}"[:400],
                           {"failure": True})


def start_wave(spec: WaveSpec) -> str:
    """Khởi chạy workflow của đợt với mã idempotent.

    Args:
        spec: Thông số đợt.

    Returns:
        Mã workflow.
    """
    with SetWorkflowID(spec.workflow_id):
        DBOS.start_workflow(wave_workflow, asdict(spec))
    return spec.workflow_id
