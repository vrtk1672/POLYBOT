param(
    [string]$Out = "run_reports/v2_20a/neural_mesh_readiness_audit.json",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$WithRuntime
)
$ErrorActionPreference = "Stop"
Push-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
try {
    $argsList = @("-m", "uv", "run", "python", "-m", "app.tools.v2_20a_neural_mesh_audit", "audit", "--out", $Out, "--base-url", $BaseUrl)
    if ($WithRuntime) { $argsList += "--with-runtime" }
    python @argsList
} finally {
    Pop-Location
}
