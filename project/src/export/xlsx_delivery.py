"""
xlsx_delivery.py — Ghi deliverable NGƯỜI DÙNG CUỐI ra .xlsx đơn sắc.

Vì sao là xlsx chứ không phải CSV (chốt 2026-09-08, US-101): CSV không lưu được độ rộng cột,
freeze pane, AutoFilter và wrap-text. Với dữ liệu thật (cột `Tóm tắt` trung bình 460 ký tự,
`Ý chính` trung bình 593 ký tự có xuống dòng), file CSV mở ra là lưới trần và người dùng phải
lặp lại ~5 thao tác định dạng MỖI NGÀY vì file mới sinh mỗi ngày. xlsx lưu được các thứ đó
một lần.

Nguyên tắc trình bày — "đơn sắc, có quy chuẩn", KHÔNG trang trí:
- Đúng 1 dòng header ở dòng 1. Không tiêu đề báo cáo, không merge cell, không dòng trống,
  không dòng tổng.
- KHÔNG màu nền, KHÔNG banding, KHÔNG màu chữ. Phân cấp chỉ bằng **in đậm** + 1 đường kẻ
  mảnh dưới header.
- Link để clickable nhưng giữ chữ đen (không dùng style `Hyperlink` xanh) — chức năng, không
  phải trang trí.
- Ngày ghi kiểu date thật + `number_format="yyyy-mm-dd"` để lọc/sắp theo ngày đúng nghĩa.

Chống formula injection: openpyxl tự đoán chuỗi mở đầu bằng `=` là CÔNG THỨC. Tiêu đề tin
tài chính mở đầu bằng `-5%…` / `+3%…` là chuyện thường, nên MỌI ô văn bản đều bị ép
`data_type="s"` (xem `_set_text`). Tham chiếu: OWASP CSV Injection.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from src.core.staging import safe_atomic_write

SHEET_NAME = "Tin theo dõi"

# Hợp đồng GIAO HÀNG: (khoá trong row dict, nhãn hiển thị, độ rộng cột, có wrap text).
# Thứ tự theo khối: định vị → phân loại (ngắn, để quét/filter) → nguồn → văn bản dài → kỹ thuật.
# 7 cột đầu đều ngắn nên vừa một màn hình; 3 cột văn bản dài nằm sau nên tràn vào vùng trống
# bên phải thay vì đẩy cột ngắn ra ngoài.
DELIVERY_FIELDS: list[tuple[str, str, int, bool]] = [
    ("date",             "Ngày",             12, False),
    ("matched_entities", "Mã theo dõi",      20, False),
    ("title",            "Tiêu đề",          48, True),
    ("sentiment",        "Sắc thái",         11, False),
    ("time_sensitivity", "Độ khẩn",          12, False),
    ("gold_status",      "Độ đầy đủ",        11, False),
    ("source_domain",    "Nguồn",            16, False),
    ("summary",          "Tóm tắt",          64, True),
    ("key_points",       "Ý chính",          64, True),
    ("implication",      "Hàm ý thị trường", 46, True),
    ("url",              "Link",             38, False),
    ("article_id",       "Mã bài",           20, False),
]

# Enum → nhãn tiếng Việt. Giá trị lạ (agent trả sai enum) được giữ NGUYÊN VĂN, không nuốt:
# nhìn thấy giá trị lạ trong file là tín hiệu để đi sửa agent.
SENTIMENT_VN = {"positive": "Tích cực", "negative": "Tiêu cực", "neutral": "Trung lập"}
TIME_SENSITIVITY_VN = {
    "urgent": "Khẩn", "today": "Trong ngày", "this_week": "Trong tuần",
    "this_month": "Trong tháng", "archive": "Lưu trữ",
}
GOLD_STATUS_VN = {"GOLD": "Đầy đủ", "L1_ONLY": "Sơ bộ"}

_VN_MAPS = {
    "sentiment": SENTIMENT_VN,
    "time_sensitivity": TIME_SENSITIVITY_VN,
    "gold_status": GOLD_STATUS_VN,
}

_HEADER_FONT = Font(bold=True)
_HEADER_BORDER = Border(bottom=Side(style="thin"))
_HEADER_ALIGN = Alignment(vertical="center", horizontal="left")
_WRAP_ALIGN = Alignment(vertical="top", wrap_text=True)
_PLAIN_ALIGN = Alignment(vertical="top")


def vn_label(field: str, value) -> str:
    """Đổi enum máy sang nhãn tiếng Việt. Giá trị ngoài từ điển giữ nguyên văn."""
    m = _VN_MAPS.get(field)
    if not m:
        return "" if value is None else str(value)
    return m.get(value, "" if value in (None, "") else str(value))


def _set_text(cell, value: str, *, align) -> None:
    """Ghi ô VĂN BẢN, chặn openpyxl diễn giải thành công thức.

    `cell.value = "=..."` khiến openpyxl gán `data_type='f'` → Excel chạy như công thức.
    Ép lại `data_type='s'` SAU khi gán để mọi chuỗi luôn là text thuần.
    """
    cell.value = value
    cell.data_type = "s"
    cell.alignment = align


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_workbook(rows: list[dict]) -> Workbook:
    """Dựng workbook 1 sheet từ các row dict (khoá theo `DELIVERY_FIELDS`)."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    for col, (_key, label, width, _wrap) in enumerate(DELIVERY_FIELDS, start=1):
        cell = ws.cell(row=1, column=col)
        _set_text(cell, label, align=_HEADER_ALIGN)
        cell.font = _HEADER_FONT
        cell.border = _HEADER_BORDER
        ws.column_dimensions[cell.column_letter].width = width

    for r_i, row in enumerate(rows, start=2):
        for col, (key, _label, _width, wrap) in enumerate(DELIVERY_FIELDS, start=1):
            cell = ws.cell(row=r_i, column=col)
            align = _WRAP_ALIGN if wrap else _PLAIN_ALIGN
            raw = row.get(key, "")

            if key == "date":
                d = _parse_date(raw)
                if d is not None:
                    cell.value = d
                    cell.number_format = "yyyy-mm-dd"
                    cell.alignment = align
                else:
                    _set_text(cell, str(raw or ""), align=align)
                continue

            if key in _VN_MAPS:
                _set_text(cell, vn_label(key, raw), align=align)
                continue

            _set_text(cell, "" if raw is None else str(raw), align=align)
            # Link bấm được nhưng KHÔNG dùng style Hyperlink (giữ đơn sắc).
            if key == "url" and str(raw or "").startswith(("http://", "https://")):
                cell.hyperlink = str(raw)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(DELIVERY_FIELDS)).column_letter}{max(ws.max_row, 1)}"
    return wb


def write_delivery_xlsx(path: str | Path, rows: list[dict]) -> tuple[Path, bool]:
    """Ghi atomic. Trả (đường dẫn ĐÃ ghi thật, True nếu phải rơi về snapshot vì file bị khoá).

    Caller BẮT BUỘC đọc cờ thứ hai: True nghĩa là file đích vẫn là bản CŨ — chưa giao hàng.
    """
    wb = build_workbook(rows)
    return safe_atomic_write(Path(path), wb.save, binary=True, fallback_on_lock=True)
