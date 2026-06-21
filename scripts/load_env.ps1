function Load-PolybotEnv {
    param(
        [string]$EnvPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env"),
        [switch]$Quiet
    )

    $result = [ordered]@{
        env_file_path = $EnvPath
        env_file_exists = $false
        env_file_loaded = $false
        loaded_keys = 0
    }

    if (-not (Test-Path $EnvPath)) {
        $env:POLYBOT_ENV_FILE_EXISTS = "false"
        $env:POLYBOT_ENV_FILE_LOADED = "false"
        $env:POLYBOT_ENV_FILE_PATH = $EnvPath
        if (-not $Quiet) {
            Write-Output "POLYBOT env: .env not found at $EnvPath"
        }
        return [pscustomobject]$result
    }

    $result.env_file_exists = $true
    foreach ($line in Get-Content -Path $EnvPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (-not $key) {
            continue
        }
        if (Test-Path "Env:$key") {
            continue
        }
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$key" -Value $value
        $result.loaded_keys += 1
    }

    $result.env_file_loaded = $true
    $env:POLYBOT_ENV_FILE_EXISTS = "true"
    $env:POLYBOT_ENV_FILE_LOADED = "true"
    $env:POLYBOT_ENV_FILE_PATH = $EnvPath

    if (-not $Quiet) {
        Write-Output "POLYBOT env: loaded .env from $EnvPath ($($result.loaded_keys) new key(s))"
    }

    return [pscustomobject]$result
}
