<#
run_daily.ps1 - Run per-user cycle (input -> final.csv) according to runbook.
See: docs/operations/daily-runbook-per-user.md

Examples:
  .\scripts\run_daily.ps1                        # FULL with stub
  .\scripts\run_daily.ps1 -Agent api             # FULL with LLM adapter
  .\scripts\run_daily.ps1 -Mode emit             # Emit task packets
  .\scripts\run_daily.ps1 -Mode emit -ExportLimit 0 # Emit all pending packets
  .\scripts\run_daily.ps1 -Mode ingest -Days 30  # Ingest and write output for last 30 days
  .\scripts\run_daily.ps1 -Mode ingest -Date all # Ingest and write output for all dates
#>
[CmdletBinding()]
param(
  [ValidateSet('full','emit','ingest')] [string]$Mode   = 'full',
  [ValidateSet('stub','api')]           [string]$Agent  = 'stub',
  [ValidateSet('missed','all')]         [string]$Review = 'missed',
  [string]$Date        = 'today',
  [int]$Days           = 0,
  [int]$ExportLimit    = 0,
  [switch]$NoCompile,
  [switch]$KeepPackets
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- Single-instance lock: chan 2 run chong nhau (Task Scheduler trung gio + chay tay) ---
# Hai run song song se doc DB nua chung (bai co L1 nhung agent_ingest chua commit) va ghi de
# output/checkpoint cua nhau. Giu handle voi FileShare::Read suot vong doi script: run khac
# khong the mo de GHI (bi chan), nhung van DOC duoc lock de bao ai dang giu.
$LockDir  = Join-Path $Root 'data'
$LockPath = Join-Path $LockDir '.pipeline.lock'
if (-not (Test-Path $LockDir)) { New-Item -ItemType Directory -Force -Path $LockDir | Out-Null }
$LockStream = $null
try {
  $LockStream = [System.IO.File]::Open(
    $LockPath,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::Read)
} catch {
  $holder = ''
  try {
    $rs = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::Open,
                                 [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    $sr = New-Object System.IO.StreamReader($rs)
    $holder = $sr.ReadToEnd().Trim()
    $sr.Close(); $rs.Dispose()
  } catch {}
  Write-Host "run_daily: MOT RUN KHAC DANG CHAY - thoat de tranh doc DB nua chung / ghi de output." -ForegroundColor Red
  Write-Host "  lock : $LockPath" -ForegroundColor DarkGray
  if ($holder) { Write-Host "  giu boi: $holder" -ForegroundColor DarkGray }
  Write-Host "  Neu chac chan khong con run nao, xoa file lock roi chay lai." -ForegroundColor DarkGray
  exit 2
}
$LockStream.SetLength(0)
$LockBytes = [System.Text.Encoding]::UTF8.GetBytes("pid=$PID started=$(Get-Date -Format o) mode=$Mode date=$Date days=$Days")
$LockStream.Write($LockBytes, 0, $LockBytes.Length)
$LockStream.Flush()

# Python executable - ignore broken .venv shim if active in shell
$Py = (Get-Command python -ErrorAction SilentlyContinue | Where-Object {
    $_.Source -notlike '*\.venv\*' -and $_.Source -notlike '*An Thanh Pham*'
} | Select-Object -First 1 -ExpandProperty Source)

if (-not $Py -or -not (Test-Path $Py)) {
    if (Test-Path 'C:\Users\anpt\AppData\Local\anaconda3\python.exe') {
        $Py = 'C:\Users\anpt\AppData\Local\anaconda3\python.exe'
    } else {
        $Py = 'python'
    }
}
$L1Out    = 'data/agent_outputs_l1'
$AgentOut = 'data/agent_outputs'

function Step([string]$Label, [string[]]$CommandArgs) {
  Write-Host "`n=== $Label ===" -ForegroundColor Cyan
  Write-Host "  $Py $($CommandArgs -join ' ')" -ForegroundColor DarkGray
  & $Py @CommandArgs
  if ($LASTEXITCODE -ne 0) { throw "FAILED at step: $Label (exit $LASTEXITCODE)" }
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
    'hierarchy' {
      Step 'run_agent_hierarchy export' @('scripts/run_agent_hierarchy.py','--export')
    }
    default {
      Write-Host "Subagent processing mode: Packets ready for invoke_subagent." -ForegroundColor Cyan
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

function CleanPackets {
  if ($KeepPackets) {
    Write-Host "`n[KeepPackets] Retaining task packets and output files." -ForegroundColor DarkGray
    return
  }
  Write-Host "`n=== Cleaning up task packets & intermediate outputs (OneDrive sync optimization) ===" -ForegroundColor Cyan
  $taskFiles = @(Get-ChildItem -Path 'data/agent_tasks' -Filter '*.task.json' -Recurse -File -ErrorAction SilentlyContinue)
  $outL1Files = @(Get-ChildItem -Path 'data/agent_outputs_l1' -Filter '*.json' -File -ErrorAction SilentlyContinue)
  $outAgentFiles = @(Get-ChildItem -Path 'data/agent_outputs' -Filter '*.json' -File -ErrorAction SilentlyContinue)

  $delTasks = 0
  $delOutputs = 0
  foreach ($f in $taskFiles) {
    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
    $delTasks++
  }
  foreach ($f in ($outL1Files + $outAgentFiles)) {
    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
    $delOutputs++
  }
  Write-Host "  Deleted $delTasks task packets and $delOutputs intermediate output files." -ForegroundColor Green
  Write-Host "  Workspace cleaned successfully." -ForegroundColor Green
}

Write-Host "run_daily: Mode=$Mode Agent=$Agent Review=$Review Date=$Date Days=$Days ExportLimit=$ExportLimit KeepPackets=$KeepPackets NoCompile=$NoCompile" -ForegroundColor Yellow

try {

switch ($Mode) {
  'emit' {
    Emit
    Write-Host "`n[EMIT DONE] Packets ready in data/agent_tasks/l1/ and data/agent_tasks/." -ForegroundColor Green
    Write-Host "-> Process with Subagents (.agents/skills/gold-financial-analyst & l1-entity-matcher)," -ForegroundColor Green
    Write-Host "   then run: .\scripts\run_daily.ps1 -Mode ingest -Days 30" -ForegroundColor Green
  }
  'ingest' {
    Ingest
    CleanPackets
  }
  'full' {
    Emit
    RunAgents
    Ingest
    CleanPackets
  }
}

Write-Host "`n=== End-to-End System Monitor Report ===" -ForegroundColor Cyan
if ($Days -gt 0) {
  & $Py 'scripts/monitor_daily.py' --days $Days --save-md
} elseif ($Date -eq 'all') {
  & $Py 'scripts/monitor_daily.py' --date all --save-md
} else {
  & $Py 'scripts/monitor_daily.py' --date $Date --save-md
}

}
finally {
  if ($LockStream) { $LockStream.Close(); $LockStream.Dispose() }
  Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
}

Write-Host "`nrun_daily COMPLETED (Mode=$Mode)." -ForegroundColor Green
Write-Host "Output: users/output/<user>/<date>.csv and users/output/_master/<date>.csv" -ForegroundColor Green
Write-Host "Daily Report: reports/daily/report-<date>.md" -ForegroundColor Green

