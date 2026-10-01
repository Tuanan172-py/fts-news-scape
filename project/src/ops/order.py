"""Đọc, ghi và áp standing order quyết định mức tự chủ của daemon."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# L0: chỉ đo và báo. L1: đủ điều kiện thì mở đợt và chạy trọn tới nạp DB, không hỏi
# từng đợt (amendment ADR 0008). Mức L2/L3 cũ (chờ duyệt, tự giao xlsx) đã gỡ; tệp lệnh
# còn ghi L2/L3 được đọc thành L1.
LEVELS = ("L0", "L1")
_LEGACY_LEVELS = {"L2": "L1", "L3": "L1"}
FAILOVER_VALUES = ("never", "ask", "auto")
PROVIDERS = ("agy", "openrouter")


@dataclass
class StandingOrder:
    """Chỉ lệnh uỷ quyền vận hành có thời hạn do người vận hành tạo.

    Attributes:
        level: Mức tự chủ ghi trong lệnh.
        valid_until: Ngày hết hạn (YYYY-MM-DD).
        provider: Provider chính.
        failover: Chính sách chuyển provider.
        created_by: Nguồn tạo hoặc sửa lệnh gần nhất.
        exists: False khi tệp chưa tồn tại.
    """

    level: str = "L0"
    valid_until: str = ""
    provider: str = "agy"
    failover: str = "never"
    created_by: str = ""
    exists: bool = False

    def effective_level(self, today: date | None = None) -> str:
        """Tính mức tự chủ có hiệu lực; lệnh thiếu hoặc hết hạn thì về L0.

        Args:
            today: Ngày đánh giá. Mặc định là hôm nay.

        Returns:
            Mức tự chủ có hiệu lực.
        """
        if not self.exists or self.level not in LEVELS:
            return "L0"
        if self.expired(today):
            return "L0"
        return self.level

    def expired(self, today: date | None = None) -> bool:
        """Cho biết lệnh đã hết hạn chưa.

        Args:
            today: Ngày đánh giá.

        Returns:
            True khi không có ngày hạn hợp lệ hoặc đã qua ngày hạn.
        """
        try:
            until = date.fromisoformat(self.valid_until)
        except ValueError:
            return True
        return (today or date.today()) > until

    def hours_left(self, today: date | None = None) -> float:
        """Tính số giờ còn lại tới hết ngày hạn.

        Args:
            today: Ngày đánh giá.

        Returns:
            Số giờ còn lại, âm khi đã hết hạn.
        """
        try:
            until = date.fromisoformat(self.valid_until)
        except ValueError:
            return -1.0
        return ((until - (today or date.today())).days + 1) * 24.0

    def digest(self) -> str:
        """Băm nội dung lệnh để ghi vào mỗi đợt.

        Returns:
            12 ký tự đầu của SHA-256.
        """
        raw = f"{self.level}|{self.valid_until}|{self.provider}|{self.failover}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def load_order(path: Path) -> StandingOrder:
    """Đọc standing order dạng `khoá: giá trị`.

    Args:
        path: Đường dẫn tệp.

    Returns:
        StandingOrder; `exists=False` khi tệp chưa có.
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
    level = _LEGACY_LEVELS.get(level, level)
    failover = data.get("failover", "never").lower()
    provider = data.get("provider", "agy").lower()
    return StandingOrder(
        level=level if level in LEVELS else "L0",
        valid_until=data.get("valid_until", ""),
        provider=provider if provider in PROVIDERS else "agy",
        failover=failover if failover in FAILOVER_VALUES else "never",
        created_by=data.get("created_by", ""),
        exists=True,
    )


def save_order(path: Path, order: StandingOrder) -> None:
    """Ghi standing order ra tệp, giữ định dạng mà `article_tick.py` đọc được.

    Args:
        path: Đường dẫn tệp.
        order: Nội dung lệnh.
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
        f"max_limit: 100\n"
    )
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def extend(order: StandingOrder, days: int, max_days: int) -> StandingOrder:
    """Gia hạn lệnh tính từ hôm nay, không vượt `max_days`.

    Args:
        order: Lệnh hiện tại.
        days: Số ngày gia hạn.
        max_days: Trần số ngày.

    Returns:
        Lệnh đã gia hạn.
    """
    days = max(1, min(int(days), int(max_days)))
    order.valid_until = (date.today() + timedelta(days=days)).isoformat()
    order.exists = True
    return order


def demote(level: str) -> str:
    """Hạ một bậc tự chủ.

    Args:
        level: Mức hiện tại.

    Returns:
        Mức thấp hơn một bậc, tối thiểu L0.
    """
    i = LEVELS.index(level) if level in LEVELS else 0
    return LEVELS[max(0, i - 1)]
