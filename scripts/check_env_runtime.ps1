$ErrorActionPreference = "Stop"

$loadEnvScript = Join-Path $PSScriptRoot "load_env.ps1"
. $loadEnvScript
$loadResult = Load-PolybotEnv

$repoRoot = Split-Path -Parent $PSScriptRoot
$envExamplePath = Join-Path $repoRoot ".env.example"
$runtimeMode = if ($env:POLYBOT_RUNTIME_MODE) { $env:POLYBOT_RUNTIME_MODE } else { "paper_safe" }
$executionBackend = if ($env:POLYBOT_EXECUTION_BACKEND) { $env:POLYBOT_EXECUTION_BACKEND } elseif ($env:EXECUTION_BACKEND) { $env:EXECUTION_BACKEND } else { "paper" }
$anthropicPresent = if ($env:ANTHROPIC_API_KEY) { $true } else { $false }
$liveEnabled = if ($env:LIVE_TRADING_ENABLED) { [System.Convert]::ToBoolean($env:LIVE_TRADING_ENABLED) } else { $false }
$killSwitch = if ($env:LIVE_KILL_SWITCH) { [System.Convert]::ToBoolean($env:LIVE_KILL_SWITCH) } else { $true }
$aiEnabled = if ($env:POLYBOT_INTELLIGENCE_AI_ENABLED) { [System.Convert]::ToBoolean($env:POLYBOT_INTELLIGENCE_AI_ENABLED) } else { $true }
$aiRuntimeState = if (-not $aiEnabled) { "DISABLED" } elseif ($anthropicPresent) { "ENABLED_KEY_PRESENT" } else { "ENABLED_KEY_MISSING" }

[pscustomobject]@{
    env_file_exists = $loadResult.env_file_exists
    env_example_exists = (Test-Path $envExamplePath)
    env_file_loaded = $loadResult.env_file_loaded
    env_file_path = $loadResult.env_file_path
    loaded_keys = $loadResult.loaded_keys
    runtime_mode = $runtimeMode
    execution_backend = $executionBackend
    live_trading_enabled = $liveEnabled
    live_kill_switch = $killSwitch
    anthropic_api_key_present = $anthropicPresent
    ai_runtime_state = $aiRuntimeState
} | ConvertTo-Json -Depth 3
