$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pytestArgs = if ($args.Count -gt 0) { $args } else { @("tests") }

Push-Location $repoRoot
try {
    docker compose --profile test run --rm test python -m pytest @pytestArgs
}
finally {
    Pop-Location
}
