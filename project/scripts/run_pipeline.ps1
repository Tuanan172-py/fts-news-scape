# run_pipeline.ps1 — 1 CHU KỲ pipeline TẤT ĐỊNH (KHÔNG cần LLM).
#   capture  : scrape → Bronze (raw_html) + articles + CSV     (src.orchestrator qua morninger)
#   derive   : Bronze → Silver → work_packages (tăng dần)       (rederive_incremental)
#   l1_route : (tùy chọn) code-first L1 → l1_tasks + packet chờ agent  — vẫn KHÔNG LLM
# Dùng cho Windows Task Scheduler. Không dừng ở đâu cần LLM.
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot          # scripts/ -> project/
Set-Location $proj
# Interpreter: uu tien $env:MONOCLE_PY, roi .venv trong repo, roi venv ngoai vung sync.
$py = @(
    $env:MONOCLE_PY,
    (Join-Path $proj ".venv\Scripts\python.exe"),
    "C:\venvs\news-scape\Scripts\python.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $py) { throw "Khong tim thay Python. Dat \$env:MONOCLE_PY tro toi python.exe cua venv." }
$env:PYTHONUTF8 = "1"

Write-Host "[$(Get-Date -Format o)] capture…"
& $py -m src.morninger --once capture
Write-Host "[$(Get-Date -Format o)] derive…"
& $py -m src.morninger --once derive

# Bỏ ghi chú dòng dưới nếu muốn chuẩn bị sẵn packet L1 cho agent (không LLM):
# & $py scripts/l1_route.py --review missed
Write-Host "[$(Get-Date -Format o)] done pipeline cycle"
