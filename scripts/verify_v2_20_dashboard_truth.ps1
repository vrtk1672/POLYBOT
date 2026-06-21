param([string]$BaseUrl = "http://127.0.0.1:8000")
$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
try {
    python -m uv run python -m app.tools.v2_20_full_system_run verify-dashboard-truth --base-url $BaseUrl
} finally {
    Pop-Location
}
