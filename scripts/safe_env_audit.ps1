param(
    [switch]$Json,
    [switch]$NoMaskedValues
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ArgsList = @()
if ($Json) { $ArgsList += "--json" }
if ($NoMaskedValues) { $ArgsList += "--no-masked-values" }

Push-Location $RepoRoot
try {
    python scripts/safe_env_audit.py @ArgsList
}
finally {
    Pop-Location
}

