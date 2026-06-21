param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [double]$DurationMinutes = 240,
    [double]$SampleMinutes = 5,
    [string]$Actor = "codex",
    [string]$Reason = "4h technical paper soak"
)

$ErrorActionPreference = "Stop"

python scripts/run_4h_technical_paper_soak.py `
    --base-url $BaseUrl `
    --duration-minutes $DurationMinutes `
    --sample-minutes $SampleMinutes `
    --actor $Actor `
    --reason $Reason
