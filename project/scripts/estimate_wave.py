"""Dự toán chi phí một đợt trước khi chạy, và đối chiếu với số thật sau khi chạy.

Đây là công cụ **để nhìn**, không phải cổng chặn. Nó không từ chối việc gì; nó chỉ
đặt con số lên bàn trước khi tiêu token và nói lại sau khi tiêu xong đã lệch bao nhiêu.

Sai số dự toán là chỉ số hạng nhất của cả hệ. Lý do: hai định mức cũ trong kho đã
lệch thực tế từ 21 tới 90 lần mà không ai phát hiện, vì chưa bao giờ có chỗ nào đối
chiếu dự toán với số đo. Chừng nào sai số còn lớn thì mọi kế hoạch ngân sách đều là
phỏng đoán.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.telemetry.dsh_usage import billed_usd, is_peak, load_pricing   # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "article"
HARNESS_DB = PROJECT_ROOT.parent / "harness.db"


def load_manifest(wave: str | None) -> dict | None:
    """Nạp mô tả đợt gần nhất hoặc theo mã đợt chỉ định.

    Args:
        wave: Mã đợt cần nạp. None thì lấy đợt mới nhất trên đĩa.

    Returns:
        Từ điển mô tả đợt, hoặc None khi không tìm thấy.
    """
    if wave:
        p = TASK_DIR / f"wave_{wave}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    files = sorted(glob.glob(str(TASK_DIR / "wave_*.json")), key=os.path.getmtime)
    if not files:
        return None
    return json.loads(Path(files[-1]).read_text(encoding="utf-8"))


def actual_from_ledger(wave: str) -> dict | None:
    """Đọc số thật của một đợt từ sổ cái nếu đã ghi.

    Args:
        wave: Mã đợt.

    Returns:
        Từ điển số đo thật, hoặc None khi đợt chưa có dòng sổ cái.
    """
    if not HARNESS_DB.exists():
        return None
    conn = sqlite3.connect(str(HARNESS_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM token_ledger WHERE wave = ? ORDER BY id DESC LIMIT 1",
            (wave,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return dict(row) if row else None


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh dự toán và đối chiếu.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi in được báo cáo, 2 khi không tìm thấy đợt nào.
    """
    ap = argparse.ArgumentParser(description="Dự toán chi phí một đợt và đối chiếu số thật")
    ap.add_argument("--wave", help="Mã đợt. Bỏ trống thì lấy đợt mới nhất")
    ap.add_argument("--peak", type=int, choices=[0, 1],
                    help="Ép khung giá. Bỏ trống thì suy từ thời điểm hiện tại")
    ap.add_argument("--json", action="store_true", help="Xuất JSON thay vì bảng")
    args = ap.parse_args(argv)

    m = load_manifest(args.wave)
    if not m:
        print("Không tìm thấy mô tả đợt nào. Chạy `article_run.py` để đóng gói trước.")
        return 2

    pricing = load_pricing()
    peak = bool(args.peak) if args.peak is not None else is_peak(pricing=pricing)
    est_miss, est_hit = m["est_miss_total"], m["est_hit_total"]
    est_out, est_quota = m["est_out_total"], m["est_quota_total"]
    est_usd = billed_usd(est_miss, est_hit, est_out, peak=peak, pricing=pricing)
    other_usd = billed_usd(est_miss, est_hit, est_out, peak=not peak, pricing=pricing)
    actual = actual_from_ledger(m["wave"])

    if args.json:
        print(json.dumps({"wave": m["wave"], "est_quota": est_quota,
                          "est_usd": round(est_usd, 6), "actual": actual},
                         ensure_ascii=False))
        return 0

    print("=" * 78)
    print(f" 💰  DỰ TOÁN ĐỢT {m['wave']} — {m['articles']:,} bài, {len(m['batches'])} lô")
    print("=" * 78)
    print(f"{'khoản':34} {'token':>12} {'ghi chú':>28}")
    print("-" * 78)
    print(f"{'Đầu vào mới (trượt cache)':34} {est_miss:>12,} {'phần đắt, tỉ lệ với nội dung':>28}")
    print(f"{'Đầu vào tái dùng (trúng cache)':34} {est_hit:>12,} {'rẻ hơn 50 lần':>28}")
    print(f"{'Đầu ra':34} {est_out:>12,} {'đắt nhất mỗi token':>28}")
    print("-" * 78)
    print(f"{'Quota tính vào hạn mức':34} {est_quota:>12,}")
    print()
    print(f"Chi phí  : ${est_usd:.4f} ({'cao điểm' if peak else 'thấp điểm'})"
          f"  ·  ${other_usd:.4f} nếu chạy khung còn lại")
    if m["articles"]:
        print(f"Mỗi bài  : {est_quota / m['articles']:,.0f} token quota "
              f"· ${est_usd / m['articles']:.6f}")

    if actual:
        print()
        print("-" * 78)
        print("ĐỐI CHIẾU VỚI SỐ THẬT ĐÃ GHI SỔ CÁI")
        print("-" * 78)
        rows = [("Đầu vào mới", est_miss, actual["miss_tokens"]),
                ("Đầu vào tái dùng", est_hit, actual["hit_tokens"]),
                ("Đầu ra", est_out, actual["out_tokens"]),
                ("Quota", est_quota, actual["quota_tokens"])]
        print(f"{'khoản':22} {'dự toán':>12} {'thật':>14} {'lệch':>10}")
        for label, e, a in rows:
            diff = ((a - e) / e * 100) if e else 0.0
            print(f"{label:22} {e:>12,} {a:>14,} {diff:>9.1f}%")
        if actual["turns_max"] > 1:
            print(f"\n⚠️  turns_max = {actual['turns_max']}: có phiên chạy quá một bước. "
                  f"Worker phải xong trong đúng một bước, soi lại persona.")
        if actual["reasoning_tokens"]:
            print(f"⚠️  reasoning = {actual['reasoning_tokens']:,} token: chế độ suy luận "
                  f"chưa tắt. Đặt `reasoningEffort: off` cho worker trong preset.")
    else:
        print()
        print("Chưa có số thật cho đợt này. Sau khi chạy xong, `article_run.py --finish`")
        print("sẽ ghi sổ cái và lệnh này sẽ hiện thêm phần đối chiếu.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
