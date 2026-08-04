def build(wb):
    ws.title = "Test Sheet"

    ledgend = (
        "Chú thích trạng thái: Not Started = Chưa bắt đầu, In Progress = Đang tiến hành, Completed = Hoàn thành, On Hold = Tạm dừng, Cancelled = Đã hủy"
    )
    ws.merge.cells("A1:M1")
    c = ws["A1"]
    c.value = ledgend
    c.font = LEDGEND_FONT
    c.fill = LEDGEND_FILL
    c.alignment = LEDGEND_ALIGNMENT

    for col_idx, (h, w) in enumerate(zip(HEADERS, COL_WIDTHS), start = 1):
        cell = ws.cell(row = 2, column = col_idx, value = h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        call.border = BORDER
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = w
