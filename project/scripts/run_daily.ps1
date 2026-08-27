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
    'api' {
      $adapter = Join-Path $Root 'scripts/agent_run.py'
      if (-not (Test-Path $adapter)) {
        throw "Missing scripts/agent_run.py. Use -Agent stub or -Mode emit for manual agent execution."
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

switch ($Mode) {
  'emit' {
    Emit
    Write-Host "`n[EMIT DONE] Packets ready in data/agent_tasks/l1/ and data/agent_tasks/." -ForegroundColor Green
    Write-Host "-> Process with Skill agent-file-processor," -ForegroundColor Green
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

Write-Host "`n=== db_status (progress check) ===" -ForegroundColor Cyan
& $Py 'scripts/db_status.py'

Write-Host "`nrun_daily COMPLETED (Mode=$Mode)." -ForegroundColor Green
Write-Host "Output: users/output/<user>/<date>.csv and users/output/_master/<date>.csv" -ForegroundColor Green

