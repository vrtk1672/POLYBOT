$ErrorActionPreference = "Stop"

$loadEnvScript = Join-Path $PSScriptRoot "load_env.ps1"
. $loadEnvScript
Load-PolybotEnv -Quiet | Out-Null

$env:POLYBOT_DATABASE_URL = "postgresql://polybot:polybot@127.0.0.1:55432/polybot"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:PHASE1_PERSISTENCE_ENABLED = "true"
$env:PHASE1_AUTO_MIGRATE = "false"
if (-not $env:POLYBOT_RUNTIME_MODE) { $env:POLYBOT_RUNTIME_MODE = "paper_safe" }
if (-not $env:POLYBOT_EXECUTION_BACKEND) {
    if ($env:EXECUTION_BACKEND) { $env:POLYBOT_EXECUTION_BACKEND = $env:EXECUTION_BACKEND } else { $env:POLYBOT_EXECUTION_BACKEND = "paper" }
}
if (-not $env:LIVE_TRADING_ENABLED) { $env:LIVE_TRADING_ENABLED = "false" }
if (-not $env:LIVE_KILL_SWITCH) { $env:LIVE_KILL_SWITCH = "true" }
$env:POLYBOT_API_HOST = "127.0.0.1"
$env:POLYBOT_API_PORT = "8000"

$anthropicPresent = if ($env:ANTHROPIC_API_KEY) { "true" } else { "false" }
$envLoaded = if ($env:POLYBOT_ENV_FILE_LOADED) { $env:POLYBOT_ENV_FILE_LOADED } else { "false" }
Write-Output ("POLYBOT runtime env: .env_loaded={0} runtime_mode={1} execution_backend={2} live_enabled={3} live_kill_switch={4} anthropic_key_present={5}" -f `
    $envLoaded,
    $env:POLYBOT_RUNTIME_MODE,
    $env:POLYBOT_EXECUTION_BACKEND,
    $env:LIVE_TRADING_ENABLED,
    $env:LIVE_KILL_SWITCH,
    $anthropicPresent)

$portInUse = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    throw "Port 8000 is already in use by PID $($portInUse[0].OwningProcess). Stop the existing runtime before starting the canonical runtime."
}

python -m uv run polybot
