param()

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $envNames = [ordered]@{}
    foreach ($file in @(".env", ".env.example")) {
        if (Test-Path $file) {
            Get-Content $file | ForEach-Object {
                if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=') {
                    if (-not $envNames.Contains($Matches[1])) {
                        $envNames[$Matches[1]] = [ordered]@{
                            env_var = $Matches[1]
                            present_in_env_file = $false
                            present_in_example = $false
                            process_present = $false
                        }
                    }
                    if ($file -eq ".env") { $envNames[$Matches[1]].present_in_env_file = $true }
                    if ($file -eq ".env.example") { $envNames[$Matches[1]].present_in_example = $true }
                }
            }
        }
    }

    foreach ($name in @($envNames.Keys)) {
        $envNames[$name].process_present = [bool][Environment]::GetEnvironmentVariable($name)
    }

    $envNames.Values | ConvertTo-Json -Depth 4
} finally {
    Pop-Location
}
