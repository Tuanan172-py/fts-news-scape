<#
.SYNOPSIS
    Wrapper goi install_market_intel_plugin.py de cai dat fpts-market-intel.
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "install_market_intel_plugin.py"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is required but not found in PATH."
    exit 1
}

& python $pythonScript
exit $LASTEXITCODE
