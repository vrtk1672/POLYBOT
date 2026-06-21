param(
    [int]$DurationSeconds = 600,
    [int]$IntervalSeconds = 60,
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$AssumeRuntimeRunning,
    [switch]$LeaveRuntimeRunning
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:POLYBOT_DATABASE_URL = "postgresql://polybot:polybot@127.0.0.1:55432/polybot"
$env:PHASE1_PERSISTENCE_ENABLED = "true"
$env:PHASE1_AUTO_MIGRATE = "false"
$env:POLYBOT_RUNTIME_MODE = "DATA_ONLY"
$env:EXECUTION_BACKEND = "paper"
$env:LIVE_TRADING_ENABLED = "false"
$env:LIVE_EXECUTION_ENABLED = "false"
$env:LIVE_KILL_SWITCH = "true"
$env:POLYBOT_HOST = "127.0.0.1"
$env:POLYBOT_PORT = "8000"

function Test-Endpoint($Url) {
    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
        return $true
    } catch {
        return $false
    }
}

Push-Location $repoRoot
try {
    powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1

    $startedProcess = $null
    if (-not $AssumeRuntimeRunning -and -not (Test-Endpoint "$BaseUrl/healthz")) {
        $startedProcess = Start-Process -FilePath "python" -ArgumentList @("-m", "uv", "run", "polybot") -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
        for ($i = 0; $i -lt 60; $i++) {
            if (Test-Endpoint "$BaseUrl/healthz") { break }
            Start-Sleep -Seconds 1
        }
    }

    if (-not (Test-Endpoint "$BaseUrl/healthz")) {
        throw "Runtime did not become healthy at $BaseUrl/healthz"
    }

    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/runtime/mode/request" -ContentType "application/json" -Body (@{
            to_mode = "DATA_ONLY"
            actor = "v2_20_smoke"
            reason = "V2.20 DATA_ONLY smoke verification"
            metadata = @{ phase = "V2.20"; live_enabled = $false }
        } | ConvertTo-Json -Depth 5) | Out-Null
    } catch {
        Write-Warning "Mode request was not accepted. Continuing with observed State Governor truth. $_"
    }

    python -m uv run python -m app.tools.v2_20_full_system_run run-smoke --mode DATA_ONLY --run-type data_only_smoke --duration-seconds $DurationSeconds --interval-seconds $IntervalSeconds --base-url $BaseUrl
} finally {
    if ($startedProcess -and -not $LeaveRuntimeRunning) {
        Stop-Process -Id $startedProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
