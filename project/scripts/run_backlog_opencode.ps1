# PowerShell script khởi chạy điều phối tự động giải phóng tồn đọng bằng OpenCode Free Tier
param(
    [int]$Waves = 40,
    [int]$Limit = 500,
    [int]$Concurrency = 2,
    [int]$Cooldown = 10,
    [double]$MaxRuntimeHours = 6.0,
    [switch]$DryRun
)

$PythonExe = "C:\venvs\news-scape\Scripts\python.exe"
$ScriptPy = Join-Path $PSScriptRoot "run_backlog_opencode.py"

$ArgsList = @(
    $ScriptPy,
    "--waves", $Waves,
    "--limit", $Limit,
    "--concurrency", $Concurrency,
    "--cooldown", $Cooldown,
    "--max-runtime-hours", $MaxRuntimeHours
)

if ($DryRun) {
    $ArgsList += "--dry-run"
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " [AUTO-RUNNER] KÍCH HOẠT TIẾN TRÌNH GIẢI PHÓNG BÀI VIẾT TỒN ĐỌNG (OPENCODE V2)" -ForegroundColor Cyan
Write-Host " • Mục tiêu: $Waves đợt | $Limit bài/đợt | Concurrency: $Concurrency" -ForegroundColor Yellow
Write-Host " • Python: $PythonExe" -ForegroundColor Gray
Write-Host "================================================================================" -ForegroundColor Cyan

& $PythonExe $ArgsList
