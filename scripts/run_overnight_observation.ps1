param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [double]$DurationHours = 8.0,
    [double]$SampleMinutes = 5.0,
    [string]$Actor = "operator",
    [string]$Reason = "overnight observation",
    [switch]$AllowYellowPreflight
)

$ErrorActionPreference = "Stop"

$argsList = @(
    "scripts/run_overnight_observation.py",
    "--base-url", $BaseUrl,
    "--duration-hours", $DurationHours,
    "--sample-minutes", $SampleMinutes,
    "--actor", $Actor,
    "--reason", $Reason
)

if ($AllowYellowPreflight) {
    $argsList += "--allow-yellow-preflight"
}

python @argsList
