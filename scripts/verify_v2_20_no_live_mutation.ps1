param(
    [Parameter(Mandatory=$true)][string]$Before,
    [Parameter(Mandatory=$true)][string]$After,
    [ValidateSet("DATA_ONLY","PAPER")][string]$Mode = "DATA_ONLY"
)
$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
try {
    python -m uv run python -m app.tools.v2_20_full_system_run verify-no-live-mutation --before $Before --after $After --mode $Mode
} finally {
    Pop-Location
}
