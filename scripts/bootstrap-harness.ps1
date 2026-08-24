# bootstrap-harness.ps1 — Khởi tạo môi trường Harness H2-H5
Param(
    [string]$DbPath = "harness.db",
    [string]$SchemaDir = "scripts/schema"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " News-Scape Harness Bootstrap (H2-H5)     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Initialize DB Schema
Write-Host "[1/3] Initializing Durable SQLite Database at $DbPath..." -ForegroundColor Yellow
python scripts/harness_cli.py --db $DbPath init --schema-dir $SchemaDir

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to initialize SQLite schema." -ForegroundColor Red
    exit 1
}

# 2. Query Contract
Write-Host "[2/3] Verifying Contract & Capabilities..." -ForegroundColor Yellow
python scripts/harness_cli.py --db $DbPath query contract

# 3. Health & Entropy Audit
Write-Host "[3/3] Running Harness Baseline Audit..." -ForegroundColor Yellow
python scripts/harness_cli.py --db $DbPath audit

Write-Host "==========================================" -ForegroundColor Green
Write-Host " Harness H2-H5 Bootstrap Completed!       " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
