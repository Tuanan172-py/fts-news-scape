# run_periodic_reports.ps1 — thu thập báo cáo định kỳ NSO (Cục Thống kê).
#
# TÁCH RIÊNG khỏi run_pipeline.ps1 có chủ đích: NSO ra ~1-3 báo cáo/THÁNG
# (công bố ~ngày 3, ~09:00 giờ VN — verified 2026-09-07). Nhét vào cycle 15 phút
# sẽ là ~96 request/ngày cho một thứ ra mỗi tháng một lần.
#
# An toàn khi chạy lặp: idempotent theo (report_type, period) — lần 2 trở đi chỉ
# `skipped_unchanged`, không fetch lại trang.
#
# Bronze ghi vào data/raw_reports/ (ROOT RIÊNG, không phải data/raw_html/) nên
# pipeline derive/handoff của bài báo KHÔNG nuốt nhầm. Xem docs/design/16.
#
# Task Scheduler (đề xuất):
#   - Trigger 1: hằng tháng, ngày 2-6, lúc 08:00 và 14:00   → bắt báo cáo tháng
#   - Trigger 2: hằng tuần, thứ Hai 09:00                    → bắt báo cáo quý/năm
#
# Exit code 1 khi có báo cáo KHÔNG đọc được kỳ (held_unparsed) hoặc capture lỗi
# → Task Scheduler báo động được, không im lặng nuốt lỗi.

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot          # scripts/ -> project/
Set-Location $proj
$py = Join-Path $proj ".venv\Scripts\python.exe"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# --after = đầu tháng hiện tại: chỉ hỏi API các bài mới, không quét lại lịch sử
$after = (Get-Date -Day 1).ToString("yyyy-MM-dd")

Write-Host "[$(Get-Date -Format o)] periodic-reports (NSO) after=$after…"
& $py 'scripts/fetch_periodic_reports.py' --after $after
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host "[$(Get-Date -Format o)] CÓ BÁO CÁO CẦN NGƯỜI XEM LẠI (held/failed)." -ForegroundColor Yellow
    Write-Host "  Xem log: logs/monocle.log — tìm '[nso] HELD'." -ForegroundColor DarkGray
    Write-Host "  Liệt kê đã có: $py scripts/fetch_periodic_reports.py --list" -ForegroundColor DarkGray
} else {
    Write-Host "[$(Get-Date -Format o)] done." -ForegroundColor Green
}
exit $code
