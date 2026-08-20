<#
run_daily.ps1 — Chạy chu kỳ per-user (input -> final.csv) theo runbook.
Xem: docs/operations/daily-runbook-per-user.md

Ví dụ:
  .\scripts\run_daily.ps1                       # FULL bằng stub (test toàn luồng, không cần LLM)
  .\scripts\run_daily.ps1 -Agent api            # FULL bằng adapter thật (cần scripts/agent_run.py)
  .\scripts\run_daily.ps1 -Mode emit            # chỉ phát packet (mốc sáng, agent thủ công)
  .\scripts\run_daily.ps1 -Mode ingest          # chỉ nạp + ghi output (mốc chiều, sau khi agent nộp)
  .\scripts\run_daily.ps1 -Review all -Date 2026-08-18 -NoCompile

Cắm Task Scheduler: powershell.exe -File <path>\scripts\run_daily.ps1 ; Start in: thư mục project.
#>
[CmdletBinding()]
param(
  [ValidateSet('full','emit','ingest')] [string]$Mode   = 'full',
  [ValidateSet('stub','api')]           [string]$Agent  = 'stub',
  [ValidateSet('missed','all')]         [string]$Review = 'missed',
  [string]$Date        = 'today',
  [int]$Days           = 0,
  [int]$ExportLimit    = 0,
  [switch]$NoCompile
)

$ErrorActionPreference = 'Stop'
# Chạy từ thư mục project (cha của scripts/)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py       = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) {
  # fallback to python in PATH
  $Py = 'python'
}
$L1Out    = 'data/agent_outputs_l1'
$AgentOut = 'data/agent_outputs'

function Step([string]$Label, [string[]]$Args) {
  Write-Host "`n=== $Label ===" -ForegroundColor Cyan
  Write-Host "  $Py $($Args -join ' ')" -ForegroundColor DarkGray
  & $Py @Args
  if ($LASTEXITCODE -ne 0) { throw "TRƯỢT ở bước: $Label (exit $LASTEXITCODE)" }
}

function Emit {
  if (-not $NoCompile) { Step 'compile_users --all'        @('scripts/compile_users.py','--all') }
  Step "l1_route --review $Review"                          @('scripts/l1_route.py','--review',$Review)
  if ($ExportLimit -gt 0) {
    Step 'agent_export --limit'                             @('scripts/agent_export.py','--limit',"$ExportLimit")
  } else {
    Step 'agent_export --all'                               @('scripts/agent_export.py','--all')
  }
}

function RunAgents {
  switch ($Agent) {
    'stub' {
      Step 'agent_stub L1'    @('scripts/agent_stub.py','--queue','l1','--out',$L1Out)
      Step 'agent_stub main'  @('scripts/agent_stub.py','--queue','main','--out',$AgentOut)
    }
    'api' {
      $adapter = Join-Path $Root 'scripts/agent_run.py'
      if (-not (Test-Path $adapter)) {
        throw "Chưa có scripts/agent_run.py (adapter LLM). Dùng -Agent stub, hoặc -Mode emit rồi xử lý agent thủ công. Xem runbook §3(C)."
      }
      Step 'agent_run L1'   @('scripts/agent_run.py','--queue','l1','--out',$L1Out)
      Step 'agent_run main' @('scripts/agent_run.py','--queue','main','--out',$AgentOut)
    }
  }
}

function Ingest {
  Step 'l1_ingest'                     @('scripts/l1_ingest.py',$L1Out)
  Step 'agent_ingest'                  @('scripts/agent_ingest.py',$AgentOut)
  if ($Days -gt 0) {
    Step "write_user_output --days $Days" @('scripts/write_user_output.py','--days',"$Days")
  } elseif ($Date -eq 'all') {
    Step "write_user_output --date all"   @('scripts/write_user_output.py','--date','all')
  } else {
    Step "write_user_output --date $Date" @('scripts/write_user_output.py','--date',$Date)
  }
}

Write-Host "run_daily: Mode=$Mode Agent=$Agent Review=$Review Date=$Date NoCompile=$NoCompile" -ForegroundColor Yellow

switch ($Mode) {
  'emit' {
    Emit
    Write-Host "`n[emit xong] Packet ở data/agent_tasks/l1/ và data/agent_tasks/." -ForegroundColor Green
    Write-Host "→ Cho agent xử lý (runbook §3), nộp *.json vào $L1Out và $AgentOut," -ForegroundColor Green
    Write-Host "  rồi chạy: .\scripts\run_daily.ps1 -Mode ingest -Date $Date" -ForegroundColor Green
  }
  'ingest' {
    Ingest
  }
  'full' {
    Emit
    RunAgents
    Ingest
  }
}

Write-Host "`n=== db_status (kiểm tra tiến độ) ===" -ForegroundColor Cyan
& $Py 'scripts/db_status.py'

Write-Host "`nrun_daily HOÀN TẤT (Mode=$Mode)." -ForegroundColor Green
Write-Host "Output: users/output/<user>/<ngày>/final.csv" -ForegroundColor Green
