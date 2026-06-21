$ErrorActionPreference = "Stop"

$loadEnvScript = Join-Path $PSScriptRoot "load_env.ps1"
. $loadEnvScript
Load-PolybotEnv -Quiet | Out-Null

$env:POLYBOT_DATABASE_URL = "postgresql://polybot:polybot@127.0.0.1:55432/polybot"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:PHASE1_PERSISTENCE_ENABLED = "true"
if (-not $env:POLYBOT_RUNTIME_MODE) { $env:POLYBOT_RUNTIME_MODE = "paper_safe" }
if (-not $env:POLYBOT_EXECUTION_BACKEND) {
    if ($env:EXECUTION_BACKEND) { $env:POLYBOT_EXECUTION_BACKEND = $env:EXECUTION_BACKEND } else { $env:POLYBOT_EXECUTION_BACKEND = "paper" }
}
if (-not $env:LIVE_TRADING_ENABLED) { $env:LIVE_TRADING_ENABLED = "false" }
if (-not $env:LIVE_KILL_SWITCH) { $env:LIVE_KILL_SWITCH = "true" }

python -m uv run app/db/migrate.py
