"""Read, write and apply the standing order that decides the autonomy level of the daemon."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# L0: stopped or locked, measure and report only. L1: mandate with a per-wave article cap;
# when conditions are met it opens a wave and runs it through DB load without asking per wave
# (ADR-0012 D5 as amended by ADR-0026.D4).
# Any level other than L0/L1 is invalid: an order file with an unknown level is read as L0 (safe).
LEVELS = ("L0", "L1")
DEFAULT_MAX_LIMIT = 100
MAX_LIMIT_CEILING = 500
FAILOVER_VALUES = ("never", "ask", "auto")
PROVIDERS = ("agy", "openrouter")


@dataclass
class StandingOrder:
    """Time-limited operations delegation created by the operator.

    Attributes:
        level: Autonomy level recorded in the order.
        valid_until: Expiry date (YYYY-MM-DD).
        provider: Primary provider.
        failover: Provider failover policy.
        max_limit: Per-wave article cap allowed by the L1 mandate.
        created_by: Source that last created or modified the order.
        exists: False when the file does not exist.
    """

    level: str = "L0"
    valid_until: str = ""
    provider: str = "agy"
    failover: str = "never"
    max_limit: int = DEFAULT_MAX_LIMIT
    created_by: str = ""
    exists: bool = False

    def effective_level(self, today: date | None = None) -> str:
        """Compute the effective autonomy level; a missing or expired order falls back to L0.

        Args:
            today: Evaluation date. Defaults to today.

        Returns:
            Effective autonomy level.
        """
        if not self.exists or self.level not in LEVELS:
            return "L0"
        if self.expired(today):
            return "L0"
        return self.level

    def expired(self, today: date | None = None) -> bool:
        """Report whether the order has expired.

        Args:
            today: Evaluation date.

        Returns:
            True when there is no valid expiry date or the expiry date has passed.
        """
        try:
            until = date.fromisoformat(self.valid_until)
        except ValueError:
            return True
        return (today or date.today()) > until

    def hours_left(self, today: date | None = None) -> float:
        """Compute the hours remaining until the end of the expiry day.

        Args:
            today: Evaluation date.

        Returns:
            Hours remaining, negative when expired.
        """
        try:
            until = date.fromisoformat(self.valid_until)
        except ValueError:
            return -1.0
        return ((until - (today or date.today())).days + 1) * 24.0

    def digest(self) -> str:
        """Hash the order content to record on each wave.

        Returns:
            First 12 characters of the SHA-256 digest.
        """
        raw = f"{self.level}|{self.valid_until}|{self.provider}|{self.failover}|{self.max_limit}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def load_order(path: Path) -> StandingOrder:
    """Read a standing order in `key: value` form.

    Args:
        path: File path.

    Returns:
        The StandingOrder; `exists=False` when the file is absent.
    """
    if not path.exists():
        return StandingOrder()
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        data[k.strip()] = v.strip().strip("'\"")
    level = data.get("level", "L0").upper()
    try:
        max_limit = int(data.get("max_limit", DEFAULT_MAX_LIMIT))
    except ValueError:
        max_limit = DEFAULT_MAX_LIMIT
    failover = data.get("failover", "never").lower()
    provider = data.get("provider", "agy").lower()
    return StandingOrder(
        level=level if level in LEVELS else "L0",
        valid_until=data.get("valid_until", ""),
        provider=provider if provider in PROVIDERS else "agy",
        failover=failover if failover in FAILOVER_VALUES else "never",
        max_limit=max(1, min(max_limit, MAX_LIMIT_CEILING)),
        created_by=data.get("created_by", ""),
        exists=True,
    )


def save_order(path: Path, order: StandingOrder) -> None:
    """Write the standing order to a file, keeping the format that `article_tick.py` can read.

    Args:
        path: File path.
        order: Order content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Mandate — uỷ quyền vận hành có thời hạn (ADR 0011, 0012, 0014).\n"
        "# Sửa qua Telegram (/level, /order extend, /provider, /failover) hoặc ops_daemon.py order.\n"
        f"level: {order.level}\n"
        f"valid_until: {order.valid_until}\n"
        f"provider: {order.provider}\n"
        f"failover: {order.failover}\n"
        f"created_by: {order.created_by}\n"
        f"max_limit: {order.max_limit}\n"
    )
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def extend(order: StandingOrder, days: int, max_days: int) -> StandingOrder:
    """Extend the order from today, not beyond `max_days`.

    Args:
        order: Current order.
        days: Number of days to extend.
        max_days: Day cap.

    Returns:
        The extended order.
    """
    days = max(1, min(int(days), int(max_days)))
    order.valid_until = (date.today() + timedelta(days=days)).isoformat()
    order.exists = True
    return order


def demote(level: str) -> str:
    """Lower the autonomy level by one step.

    Args:
        level: Current level.

    Returns:
        The level one step lower, at minimum L0.
    """
    i = LEVELS.index(level) if level in LEVELS else 0
    return LEVELS[max(0, i - 1)]
