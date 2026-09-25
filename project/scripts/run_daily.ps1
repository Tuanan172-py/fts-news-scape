<#
run_daily.ps1 - Run per-user cycle (input -> final.csv) according to runbook.
See: docs/operations/daily-runbook-per-user.md

KHONG GIA LAP: script nay KHONG duoc mac dinh goi bat ky mo phong/stub LLM nao (AGENTS.md SS6C -
Cam Tuyet doi Gia lap Tri tue Agent bang Heuristic Script). Bai chua co Subagent xu ly that se
o nguyen trang thai cho (L1_ONLY / work_items pending) - KHONG duoc dien du lieu gia de "cho day".

MODE 'full' DA BI BO (ADR 0008 SS2.5): no KHONG chay Gold (ValidateSet chan nhanh goi agent, nhanh
con lai chi in huong dan) nhung VAN xoa packet - tao vong lap tu huy: xuat packet, in chu, ingest
khi chua co output, roi xoa sach packet vua xuat. Viec goi tac nhan nam o buoc giua, do nguoi van
hanh chu dong kich hoat qua scripts/auto_pilot.py (co cong xin quyen).

Examples:
  .\scripts\run_daily.ps1 -Mode emit             # Emit task packets, tu giao cho Subagent xu ly
  .\scripts\run_daily.ps1 -Mode emit -ExportLimit 0 # Emit all pending packets
  .\scripts\run_daily.ps1 -Mode ingest -Days 30  # Ingest and write output for last 30 days
  .\scripts\run_daily.ps1 -Mode ingest -Date all # Ingest and write output for all dates
  .\scripts\run_daily.ps1 -Mode ingest -CleanPackets  # Ingest + don packet DA HOAN TAT
#>
# ======================================================================================
# TEP NAY THUOC LANE L1/GOLD DA NGUNG (ADR 0010, 2026-09-23). KHONG CHAY.
#
# Ham Emit con goi l1_route.py, l1_ingest.py --code-first va agent_export.py, ca ba deu bi
# AGENTS.md SS6 cam. Khong Task Scheduler nao dang ky tep nay, nen no la ma chet; nhung de
# nguyen thi mot lan goi tay se sinh viec cho mot lane da ngung va lam nhieu bo dem.
#
# Duong xu ly duy nhat la Article Lane:
#   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
#   & "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave <ma> --date <ngay> --limit <n>
#   & "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave <ma> --finish
#   & "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date <ngay>
# Xem .agents/dsh/RUNBOOK-article-lane.md.
#
# Go han tep nay theo plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md SS3.1.
# ======================================================================================
[CmdletBinding()]
param(
  [ValidateSet('emit','ingest')]        [string]$Mode   = 'emit',
  [ValidateSet('missed','all')]         [string]$Review = 'missed',
  [string]$Date        = 'today',
  [int]$Days           = 0,
  [int]$ExportLimit    = 0,
  [switch]$NoCompile,
  # Mac dinh GIU packet. Truoc day mac dinh la xoa (-KeepPackets moi giu) nen mot lan chay
  # nham xoa trang hang doi chua ai xu ly.
  [switch]$CleanPackets
)

# Lane L1/Gold da ngung (ADR 0010). Ham Emit con goi l1_route.py, l1_ingest.py --code-first va
# agent_export.py, ca ba deu bi AGENTS.md SS6 cam. Khong Task Scheduler nao dang ky tep nay nen
# no la ma chet; nhung de nguyen thi mot lan goi tay se sinh viec cho mot lane da ngung.
# Duong xu ly duy nhat la Article Lane: scripts/article_run.py. Xem RUNBOOK-article-lane.md.
Write-Error ('run_daily.ps1 thuoc lane L1/Gold da ngung (ADR 0010). Dung Article Lane: ' +
             'scripts/article_run.py --wave <ma> --date <ngay> --limit <n>, roi --finish. ' +
             'Xem .agents/dsh/RUNBOOK-article-lane.md.')
exit 2

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
  # Vat chat hoa ket qua TRA DANH MUC tat dinh (route=resolved) -> l1_outputs. Khong co buoc
  # nay thi bai code-first DA nhan ra ma cua nguoi dung se nam 'pending' vinh vien va khong
  # bao gio qua duoc cong `articles JOIN l1_outputs`. Xem docs/decisions/0003-*.
  # -Review missed van dung: Agent chi can lo phan route=needs_agent.
  Step 'l1_ingest --code-first'                             @('scripts/l1_ingest.py','--code-first')
  if ($ExportLimit -gt 0) {
    Step 'agent_export --limit'                             @('scripts/agent_export.py','--limit',"$ExportLimit")
  } else {
    Step 'agent_export --all'                               @('scripts/agent_export.py','--all')
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

function CleanPacketsStep {
  # Chi xoa packet CO BANG CHUNG HOAN TAT trong DB (l1_outputs/agent_outputs dod_pass=1).
  # Lenh xoa trang cu (-Recurse tren data/agent_tasks) da tung co the xoa hang tram packet
  # L1 chua ai xu ly - xem ADR 0008 va docs/OPEN-ITEMS.md SSA0-2.
  if (-not $CleanPackets) {
    Write-Host "`n[packets] Giu nguyen task packet (mac dinh). Dung -CleanPackets de don packet da hoan tat." -ForegroundColor DarkGray
    return
  }
  Step 'clean_completed_packets --apply' @('scripts/maintenance/clean_completed_packets.py','--apply')
}

Write-Host "run_daily: Mode=$Mode Review=$Review Date=$Date Days=$Days ExportLimit=$ExportLimit CleanPackets=$CleanPackets NoCompile=$NoCompile" -ForegroundColor Yellow

try {

switch ($Mode) {
  'emit' {
    Emit
    Write-Host "`n[EMIT DONE] Packets ready in data/agent_tasks/l1/ and data/agent_tasks/." -ForegroundColor Green
    Write-Host "-> Xu ly packet bang Subagent that (.agents/skills/gold-financial-analyst & l1-entity-matcher)," -ForegroundColor Green
    Write-Host "   hoac chay: python scripts/auto_pilot.py   (co cong xin quyen truoc khi tieu thu token)" -ForegroundColor Green
    Write-Host "   roi: .\scripts\run_daily.ps1 -Mode ingest -Days 30" -ForegroundColor Green
  }
  'ingest' {
    Ingest
    CleanPacketsStep
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

