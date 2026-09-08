"""
make_user_template.py — Sinh template entities.xlsx đơn giản cho user nhập.

Template gồm:
  * sheet `entities`: cột tickers/etfs/indices/exchanges/industries/entities (nhập 1 giá trị/dòng).
  * sheet `meta`: user, note.
  * sheet `huong_dan`: hướng dẫn tiếng Việt + trỏ tới data/entities/entities.xlsx để tra mã.
  * Dropdown (data-validation) cho `exchanges` (danh sách nhỏ, cố định).

Usage:
    python scripts/make_user_template.py                       # ghi users/template/entities_template.xlsx
    python scripts/make_user_template.py --seed AnPT           # tạo users/input/AnPT/entities.xlsx từ config yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                            # noqa: E402
from openpyxl import Workbook                          # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.users.compile import (                        # noqa: E402
    DEFAULT_INPUT_ROOT, DEFAULT_SUBSCRIPTIONS_ROOT, GROUP_KEYS, REPO_ROOT, USERS_CONFIG_DIR,
    write_user_csv, write_user_xlsx,
)

force_utf8_stdio()

EXCHANGES = ["HOSE", "HNX", "UPCOM"]

HUONG_DAN = [
    ["Mục", "Hướng dẫn"],
    ["1. Tên file", "Đặt tên theo cú pháp {username}_news.csv (vd: AnPT_news.csv)"],
    ["2. Cột", "tickers, etfs, indices, exchanges, industries, nations, themes, assets, institutions"],
    ["3. Tra cứu mã", "Mở data/entities/entities.xlsx để xem bảng mã chuẩn"],
    ["4. Bật/tắt", "users/subscriptions/manifest.yaml (mặc định không ghi là bật)"],
]

HUONG_DAN_LINES = [
    "# ==============================================================================",
    "# HƯỚNG DẪN ĐĂNG KÝ DANH MỤC THEO DÕI TIN TỨC (NEWS-SCAPE)",
    "# ==============================================================================",
    "# 1. Đặt tên file theo cú pháp: {username}_news.csv (Ví dụ: AnPT_news.csv, Bob_news.csv).",
    "# 2. File CSV gồm các cột tương ứng với các nhóm thực thể:",
    "#    - tickers: Mã cổ phiếu 3 ký tự (vd: HPG, FPT, VNM, MWG...)",
    "#    - etfs: Mã quỹ ETF (vd: E1VFVN30, FUEVFVND...)",
    "#    - indices: Mã chỉ số thị trường (vd: VNINDEX, VN30, HNX30...)",
    "#    - exchanges: Mã sàn giao dịch (HOSE, HNX, UPCOM)",
    "#    - industries: Mã ngành GICS (vd: THEP, NGAN_HANG, BAT_DONG_SAN, BAN_LE...)",
    "#    - nations: Mã quốc gia/địa chính trị (vd: MY, TRUNG_QUOC, EU, NHAT_BAN...)",
    "#    - themes: Mã chủ đề vĩ mô (vd: LAI_SUAT, TY_GIA, LAM_PHAT, DAU_TU_CONG, FDI...)",
    "#    - assets: Mã loại tài sản (vd: TRAI_PHIEU, CO_PHIEU, VANG, DAU_THO...)",
    "#    - institutions: Mã định chế/ngân hàng TW (vd: NHNN, UBCKNN, BO_TAI_CHINH, FED...)",
    "# 3. Tra cứu toàn bộ mã hợp lệ tại file: data/entities/entities.xlsx hoặc entities.json",
    "# 4. Bật/tắt nhận tin tại: users/subscriptions/manifest.yaml (mặc định không ghi là BẬT)",
    "# ==============================================================================",
]


def build_csv_template(path: Path) -> Path:
    """Sinh file template CSV phẳng có chú thích rõ ràng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(HUONG_DAN_LINES)
    lines.append(",".join(GROUP_KEYS))
    # Dòng ví dụ mẫu
    lines.append("HPG,E1VFVN30,VNINDEX,HOSE,THEP,MY,LAI_SUAT,TRAI_PHIEU,NHNN,")
    lines.append("FPT,,VN30,HNX,NGAN_HANG,TRUNG_QUOC,TY_GIA,VANG,UBCKNN,")
    lines.append("MWG,,,,BAT_DONG_SAN,EU,DAU_TU_CONG,,,")
    
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def build_template(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "entities"
    ws.append(list(GROUP_KEYS))
    ws.append(["HPG", "E1VFVN30", "VNINDEX", "HOSE", "THEP", "MY", "LAI_SUAT", "TRAI_PHIEU", "NHNN", None])
    ws.freeze_panes = "A2"
    # dropdown cho exchanges (cột D)
    dv_ex = DataValidation(type="list", formula1='"%s"' % ",".join(EXCHANGES), allow_blank=True)
    ws.add_data_validation(dv_ex); dv_ex.add("D2:D200")

    wb.save(path)
    return path


def seed_from_yaml(name: str, target_dir: Path | None = None) -> Path:
    """Tạo users/subscriptions/<name>_news.csv từ config yaml hiện có (giữ dữ liệu mẫu)."""
    yaml_path = USERS_CONFIG_DIR / f"{name}.yaml"
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {} if yaml_path.exists() else {}
    dest_dir = target_dir or DEFAULT_SUBSCRIPTIONS_ROOT
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{name}_news.csv"
    return write_user_csv(out, doc, {"user": name})


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", metavar="NAME", help="seed users/subscriptions/<NAME>_news.csv từ config yaml")
    ap.add_argument("--out-csv", default=str(DEFAULT_SUBSCRIPTIONS_ROOT / "_template_news.csv"))
    ap.add_argument("--out-xlsx", default=str(REPO_ROOT / "users" / "template" / "entities_template.xlsx"))
    args = ap.parse_args(argv)

    if args.seed:
        p = seed_from_yaml(args.seed)
        print(f"seeded → {p}")
        
    p_csv = build_csv_template(Path(args.out_csv))
    print(f"csv template → {p_csv}")
    
    p_xlsx = build_template(Path(args.out_xlsx))
    print(f"xlsx template → {p_xlsx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

