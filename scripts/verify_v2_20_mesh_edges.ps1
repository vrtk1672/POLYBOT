$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
try {
    python -m uv run python -m app.tools.v2_20a_neural_mesh_audit edges
} finally {
    Pop-Location
}
