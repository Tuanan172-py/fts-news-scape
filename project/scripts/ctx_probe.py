"""Đo áp suất ngữ cảnh của phiên DSH và khuyến nghị thời điểm bàn giao."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.telemetry.dsh_usage import (                # noqa: E402
    iter_sessions,
    load_pricing,
)

force_utf8_stdio()

GREEN, AMBER, RED = "🟢", "🟡", "🔴"


def classify(ratio: float, amber: float, red: float) -> tuple[str, str]:
    """Xếp mức áp suất ngữ cảnh và nêu hành động tương ứng.

    Ngưỡng được đặt thấp hơn nhiều so với mốc nén tự động 80% của DSH, vì DSH không
    cắt tỉa gì trước mốc đó: bộ cắt kết quả công cụ không đăng ký listener nào nên chỉ
    chạy bên trong một lượt nén. Nói cách khác, không có cơ chế nào giữ ngữ cảnh gọn
    trước 80%, nên việc canh phải do phía dự án làm.

    Args:
        ratio: Tỷ lệ lấp đầy cửa sổ ngữ cảnh, từ 0 đến 1.
        amber: Ngưỡng cảnh báo vàng.
        red: Ngưỡng cảnh báo đỏ.

    Returns:
        Cặp gồm biểu tượng mức và mô tả hành động cần làm.
    """
    if ratio >= red:
        return RED, "DỪNG NGAY sau batch hiện tại, sinh handoff rồi mở phiên mới"
    if ratio >= amber:
        return AMBER, "Hoàn tất wave đang chạy rồi đóng phiên; KHÔNG mở wave mới"
    return GREEN, "Chạy bình thường"


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh đo áp suất ngữ cảnh.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi áp suất dưới ngưỡng đỏ, 1 khi đã chạm ngưỡng đỏ.
    """
    ap = argparse.ArgumentParser(description="Đo áp suất ngữ cảnh phiên DSH")
    ap.add_argument("--cwd-filter", default="news-scape",
                    help="Chỉ xét phiên có thư mục làm việc chứa chuỗi này")
    ap.add_argument("--top", type=int, default=5, help="Số phiên hiển thị")
    ap.add_argument("--json", action="store_true", help="Xuất JSON thay vì bảng")
    args = ap.parse_args(argv)

    pricing = load_pricing()
    th = pricing.get("watch_thresholds") or {}
    amber = float(th.get("context_pressure_amber", 0.25))
    red = float(th.get("context_pressure_red", 0.40))

    sessions = iter_sessions(args.cwd_filter)
    if not sessions:
        print("Không tìm thấy phiên DSH nào cho bộ lọc đã cho. "
              "Kiểm tra DSH_HOME hoặc chạy thử một phiên trước.")
        return 0

    newest = sessions[0]
    icon, action = classify(newest.pressure_ratio, amber, red)

    if args.json:
        print(json.dumps({
            "session_id": newest.session_id,
            "pressure_tokens": newest.pressure_tokens,
            "context_window": newest.context_window,
            "ratio": round(newest.pressure_ratio, 4),
            "level": {GREEN: "green", AMBER: "amber", RED: "red"}[icon],
            "action": action,
            "turns": newest.turns,
        }, ensure_ascii=False, indent=2))
        return 1 if icon == RED else 0

    print("=" * 78)
    print(" 🧠  ÁP SUẤT NGỮ CẢNH PHIÊN DSH")
    print("=" * 78)
    print(f"Phiên mới nhất : {newest.session_id}")
    print(f"Áp suất        : {newest.pressure_tokens:,} / {newest.context_window:,} "
          f"({newest.pressure_ratio:.1%}) {icon}")
    print(f"Ngưỡng         : xanh <{amber:.0%} · vàng {amber:.0%}–{red:.0%} · đỏ >{red:.0%}")
    print(f"Khuyến nghị    : {action}")
    print()
    print(f"{'phiên':32} {'áp suất':>10} {'lượt':>6} {'quota':>13}")
    print("-" * 78)
    for s in sessions[:args.top]:
        mark = classify(s.pressure_ratio, amber, red)[0]
        print(f"{s.session_id[:32]:32} {s.pressure_ratio:>9.1%}{mark} "
              f"{s.turns:>6} {s.quota_tokens:>13,}")
    print("=" * 78)
    return 1 if icon == RED else 0


if __name__ == "__main__":
    raise SystemExit(main())
