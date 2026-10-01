"""Phân loại lỗi provider và giữ circuit breaker bền cho từng provider."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from src.ops.store import OpsStore, iso, now_vn, parse_iso

OK, TIMEOUT, NETWORK, QUOTA, AUTH, EMPTY, FATAL = (
    "OK", "TIMEOUT", "NETWORK", "QUOTA", "AUTH", "EMPTY", "FATAL")

# Thứ tự nghiêm trọng khi gộp nhiều lô về một lớp lỗi của cả đợt.
SEVERITY_ORDER = (AUTH, QUOTA, NETWORK, TIMEOUT, EMPTY, FATAL, OK)
PROVIDER_CLASSES = (AUTH, QUOTA, NETWORK, TIMEOUT, EMPTY)

_PATTERNS: list[tuple[str, re.Pattern]] = [
    (AUTH, re.compile(r"\b40[13]\b|unauthenticated|unauthori[sz]ed|permission[_ ]denied|"
                      r"not logged in|login required|please log ?in|re-?authenticate|"
                      r"invalid[_ ]credentials|token (?:has )?expired|đăng nhập", re.I)),
    (QUOTA, re.compile(r"\b429\b|resource[_ ]exhausted|quota|rate[_ ]?limit|hạn mức", re.I)),
    (NETWORK, re.compile(r"getaddrinfo|name resolution|connection (?:reset|refused|aborted|error)|"
                         r"connecterror|network is unreachable|no route to host|"
                         r"ssl(?:error)?|econn|enotfound|\b50[234]\b|unavailable|bad gateway|"
                         r"max retries exceeded|failed to establish", re.I)),
    (TIMEOUT, re.compile(r"timeout|timed out|quá thời gian|hết thời gian", re.I)),
    (EMPTY, re.compile(r"soft_fail|bóc tách json thất bại|empty (?:output|response)|"
                       r"stdout rỗng", re.I)),
]

# Trạng thái lô mà runner in ra, ánh xạ sang lớp lỗi của breaker.
RUNNER_STATUS_MAP = {
    "OK": OK, "PARTIAL": OK, "QUOTA": QUOTA, "TIMEOUT": TIMEOUT, "RETRYABLE": NETWORK,
    "SOFT_FAIL": EMPTY, "VIOLATION": FATAL,
}


def classify(text: str) -> str:
    """Phân loại một đoạn lỗi thành lớp lỗi provider.

    Args:
        text: stderr, thông điệp lỗi hoặc đuôi nhật ký.

    Returns:
        Một trong AUTH, QUOTA, NETWORK, TIMEOUT, EMPTY, FATAL.
    """
    for cls, pat in _PATTERNS:
        if pat.search(text or ""):
            return cls
    return FATAL


def classify_batch(status: str, error: str) -> str:
    """Phân loại kết quả một lô theo trạng thái runner và thông điệp lỗi.

    Args:
        status: Trạng thái runner (OK, PARTIAL, QUOTA, TIMEOUT, FATAL, ...).
        error: Thông điệp lỗi kèm theo.

    Returns:
        Lớp lỗi của breaker.
    """
    status = (status or "").upper()
    if status == "RETRYABLE":
        found = classify(error)
        return found if found in (AUTH, QUOTA) else NETWORK
    if status in RUNNER_STATUS_MAP:
        return RUNNER_STATUS_MAP[status]
    return classify(error)


def worst(classes: list[str]) -> str:
    """Chọn lớp lỗi nghiêm trọng nhất.

    Args:
        classes: Danh sách lớp lỗi.

    Returns:
        Lớp nghiêm trọng nhất, OK khi danh sách rỗng.
    """
    present = set(classes)
    for cls in SEVERITY_ORDER:
        if cls in present:
            return cls
    return OK


@dataclass
class BreakerState:
    """Ảnh chụp trạng thái breaker của một provider.

    Attributes:
        provider: Tên provider.
        state: CLOSED, OPEN hoặc HALF_OPEN.
        consecutive_failures: Số lỗi provider liên tiếp.
        last_class: Lớp lỗi gần nhất.
        reopen_at: Thời điểm được thử lại, None nghĩa là chờ người.
        reason: Lý do mở.
    """

    provider: str
    state: str
    consecutive_failures: int
    last_class: str | None
    reopen_at: str | None
    reason: str | None


class Breakers:
    """Circuit breaker bền theo provider, lưu trong `provider_breakers`.

    Attributes:
        store: Store vận hành.
        cfg: Mục `breaker` của cấu hình.
    """

    def __init__(self, store: OpsStore, cfg: dict) -> None:
        """Gắn store và cấu hình.

        Args:
            store: Store vận hành.
            cfg: Mục `breaker` của cấu hình.
        """
        self.store = store
        self.cfg = cfg

    def get(self, provider: str) -> BreakerState:
        """Đọc trạng thái breaker, mặc định CLOSED.

        Args:
            provider: Tên provider.

        Returns:
            Trạng thái breaker.
        """
        with self.store.conn() as c:
            row = c.execute("SELECT * FROM provider_breakers WHERE provider = ?",
                            (provider,)).fetchone()
        if not row:
            return BreakerState(provider, "CLOSED", 0, None, None, None)
        return BreakerState(provider, row["state"], row["consecutive_failures"],
                            row["last_class"], row["reopen_at"], row["reason"])

    def _save(self, s: BreakerState, *, opened: bool = False) -> None:
        with self.store.conn() as c:
            c.execute(
                "INSERT INTO provider_breakers(provider, state, consecutive_failures, last_class,"
                " opened_at, reopen_at, reason, updated_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(provider) DO UPDATE SET state=excluded.state, "
                "consecutive_failures=excluded.consecutive_failures, "
                "last_class=excluded.last_class, "
                "opened_at=COALESCE(excluded.opened_at, provider_breakers.opened_at), "
                "reopen_at=excluded.reopen_at, reason=excluded.reason, "
                "updated_at=excluded.updated_at",
                (s.provider, s.state, s.consecutive_failures, s.last_class,
                 iso() if opened else None, s.reopen_at, s.reason, iso()))

    def allow(self, provider: str) -> tuple[bool, BreakerState]:
        """Quyết định có được gọi provider không; OPEN quá hạn thì chuyển HALF_OPEN.

        Args:
            provider: Tên provider.

        Returns:
            Cặp (được phép, trạng thái sau khi đánh giá).
        """
        s = self.get(provider)
        if s.state == "CLOSED" or s.state == "HALF_OPEN":
            return True, s
        reopen = parse_iso(s.reopen_at)
        if reopen is not None and now_vn() >= reopen:
            s.state = "HALF_OPEN"
            self._save(s)
            self.store.emit("breaker.half_open", f"{provider}: thử lại sau thời gian mở",
                            level="info", data={"provider": provider})
            return True, s
        return False, s

    def record(self, provider: str, cls: str) -> str | None:
        """Ghi một kết quả gọi provider và chuyển trạng thái breaker.

        Args:
            provider: Tên provider.
            cls: Lớp kết quả (OK hoặc lớp lỗi).

        Returns:
            `opened`, `closed` khi có chuyển trạng thái, ngược lại None.
        """
        s = self.get(provider)
        if cls == OK:
            was_open = s.state != "CLOSED"
            if s.consecutive_failures or was_open:
                s.state, s.consecutive_failures, s.reopen_at, s.reason = "CLOSED", 0, None, None
                self._save(s)
            return "closed" if was_open else None
        if cls not in PROVIDER_CLASSES:
            return None
        s.consecutive_failures = (s.consecutive_failures + 1
                                  if s.last_class == cls or s.state == "HALF_OPEN" else 1)
        s.last_class = cls
        minutes: int | None
        if cls == AUTH:
            trip, minutes = True, None
        elif cls == QUOTA:
            trip, minutes = True, int(self.cfg.get("quota_open_minutes", 300))
        elif cls == NETWORK:
            trip = s.consecutive_failures >= int(self.cfg.get("network_trip", 3))
            minutes = int(self.cfg.get("network_open_minutes", 10))
        elif cls == TIMEOUT:
            trip = s.consecutive_failures >= int(self.cfg.get("timeout_trip", 3))
            minutes = int(self.cfg.get("timeout_open_minutes", 30))
        else:
            trip = s.consecutive_failures >= int(self.cfg.get("empty_trip", 2))
            minutes = int(self.cfg.get("timeout_open_minutes", 30))
        if s.state == "HALF_OPEN":
            trip = True
        if not trip:
            self._save(s)
            return None
        already_open = s.state == "OPEN"
        s.state = "OPEN"
        s.reopen_at = iso(now_vn() + timedelta(minutes=minutes)) if minutes else None
        s.reason = cls
        self._save(s, opened=not already_open)
        return None if already_open else "opened"

    def reset(self, provider: str) -> None:
        """Đóng breaker theo lệnh của người vận hành.

        Args:
            provider: Tên provider.
        """
        self._save(BreakerState(provider, "CLOSED", 0, None, None, None))

    def all(self) -> list[BreakerState]:
        """Liệt kê mọi breaker đã có bản ghi.

        Returns:
            Danh sách trạng thái breaker.
        """
        with self.store.conn() as c:
            rows = c.execute("SELECT provider FROM provider_breakers ORDER BY provider").fetchall()
        return [self.get(r["provider"]) for r in rows]
