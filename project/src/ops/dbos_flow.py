"""Wrap the wave lifecycle in a durable DBOS workflow where each stage is a checkpointed step."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dbos import DBOS, SetWorkflowID

from src.ops.config import OpsPaths
from src.ops.wave_flow import DirectOps, WaveSpec, WaveSteps, drive_wave

# Pinned application version: DBOS recovers only workflows of the same version, and the
# default version is a hash of the source code, so editing code mid-run would orphan an
# interrupted wave. Bump this number only when the order or count of `drive_wave` steps changes.
APP_VERSION = "ops-v2"

_runtime: dict[str, Any] = {}


def init_dbos(paths: OpsPaths) -> None:
    """Initialize DBOS with a dedicated SQLite system database outside OneDrive.

    Args:
        paths: Operations paths.
    """
    url = "sqlite:///" + str(paths.dbos_db).replace("\\", "/")
    DBOS(config={"name": "news-scape-ops", "system_database_url": url,
                 "application_version": APP_VERSION, "log_level": "WARNING"})


def bind(steps: WaveSteps, cfg: dict) -> None:
    """Bind the step set and configuration for the DBOS steps.

    Args:
        steps: WaveSteps of the daemon.
        cfg: Full configuration.
    """
    _runtime["direct"] = DirectOps(steps)
    _runtime["cfg"] = cfg


def _direct() -> DirectOps:
    return _runtime["direct"]


@DBOS.step()
def st_preflight(spec: dict) -> list:
    """Run the durable preflight step.

    Args:
        spec: WaveSpec as a dict.

    Returns:
        Preflight result from the wave steps.
    """
    return _direct().preflight(spec)


@DBOS.step()
def st_prepare(spec: dict) -> int:
    """Run the durable packing step.

    Args:
        spec: WaveSpec as a dict.

    Returns:
        Number of articles packed.
    """
    return _direct().prepare(spec)


@DBOS.step()
def st_analyze(spec: dict, round_no: int) -> dict:
    """Run the durable analysis or repair step.

    Args:
        spec: WaveSpec as a dict.
        round_no: Analysis or repair round number.

    Returns:
        Round result from the wave steps.
    """
    return _direct().analyze(spec, round_no)


@DBOS.step()
def st_stop_requested(spec: dict) -> bool:
    """Run the durable step that reads the stop flag at the boundary before DB load.

    Args:
        spec: WaveSpec as a dict.

    Returns:
        True when a stop was requested.
    """
    return _direct().stop_requested(spec)


@DBOS.step()
def st_finish(spec: dict) -> list:
    """Run the durable finish and DB load step.

    Args:
        spec: WaveSpec as a dict.

    Returns:
        Finish result from the wave steps.
    """
    return _direct().finish(spec)


@DBOS.step()
def st_finalize(spec: dict, status: str, reason: str, flags: dict) -> str:
    """Run the durable step that records the final wave status.

    Args:
        spec: WaveSpec as a dict.
        status: Final wave status.
        reason: Reason for the final status.
        flags: Outcome flags.

    Returns:
        Final status recorded.
    """
    return _direct().finalize(spec, status, reason, flags)


class DbosOps:
    """Step set of `drive_wave` that routes through DBOS steps."""

    def preflight(self, spec: dict) -> list:
        """Run preflight as a DBOS step.

        Args:
            spec: WaveSpec as a dict.

        Returns:
            Preflight result.
        """
        return st_preflight(spec)

    def prepare(self, spec: dict) -> int:
        """Run packing as a DBOS step.

        Args:
            spec: WaveSpec as a dict.

        Returns:
            Number of articles packed.
        """
        return st_prepare(spec)

    def analyze(self, spec: dict, round_no: int) -> dict:
        """Run analysis or repair as a DBOS step.

        Args:
            spec: WaveSpec as a dict.
            round_no: Analysis or repair round number.

        Returns:
            Round result.
        """
        return st_analyze(spec, round_no)

    def stop_requested(self, spec: dict) -> bool:
        """Read the stop flag as a DBOS step.

        Args:
            spec: WaveSpec as a dict.

        Returns:
            True when a stop was requested.
        """
        return st_stop_requested(spec)

    def finish(self, spec: dict) -> list:
        """Run finish and DB load as a DBOS step.

        Args:
            spec: WaveSpec as a dict.

        Returns:
            Finish result.
        """
        return st_finish(spec)

    def finalize(self, spec: dict, status: str, reason: str, flags: dict) -> str:
        """Record the final wave status as a DBOS step.

        Args:
            spec: WaveSpec as a dict.
            status: Final wave status.
            reason: Reason for the final status.
            flags: Outcome flags.

        Returns:
            Final status recorded.
        """
        return st_finalize(spec, status, reason, flags)


@DBOS.workflow()
def wave_workflow(spec: dict) -> str:
    """Run the durable workflow of one wave.

    Args:
        spec: WaveSpec as a dict.

    Returns:
        Final status.
    """
    try:
        return drive_wave(spec, DbosOps(), _runtime["cfg"])
    except Exception as exc:  # noqa: BLE001 — a step that raises must move the wave to FAILED, not leave it stuck
        return st_finalize(spec, "FAILED", f"Bước của đợt ném lỗi: {exc}"[:400],
                           {"failure": True})


def start_wave(spec: WaveSpec) -> str:
    """Start the wave workflow under an idempotent workflow id.

    Args:
        spec: Wave parameters.

    Returns:
        Workflow identifier.
    """
    with SetWorkflowID(spec.workflow_id):
        DBOS.start_workflow(wave_workflow, asdict(spec))
    return spec.workflow_id
