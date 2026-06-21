$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
try {
    python -m uv run python -m app.tools.v2_20_full_system_run verify-ai-cost-cache
} finally {
    Pop-Location
}
