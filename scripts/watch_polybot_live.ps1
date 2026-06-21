param(
    [int]$RefreshSeconds = 5,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "SilentlyContinue"
$Host.UI.RawUI.WindowTitle = "POLYBOT Live Terminal"

function Get-Api($Path) {
    try {
        return Invoke-RestMethod "$BaseUrl$Path" -TimeoutSec 5
    } catch {
        return $null
    }
}

function Val($Obj, [string[]]$Names, $Default = "-") {
    if ($null -eq $Obj) { return $Default }
    foreach ($Name in $Names) {
        if ($Obj.PSObject.Properties.Name -contains $Name) {
            $V = $Obj.$Name
            if ($null -ne $V -and "$V" -ne "") { return $V }
        }
    }
    return $Default
}

function Badge($Text) {
    $T = "$Text"
    if ($T -match "ON|OK|GREEN|HEALTHY|READY|APPROVE|ELIGIBLE|COMPLETE") {
        Write-Host $T -ForegroundColor Green -NoNewline
    } elseif ($T -match "OFF|STOP|RED|ERROR|FAILED|BLOCKED|MISSING|STALE") {
        Write-Host $T -ForegroundColor Red -NoNewline
    } elseif ($T -match "YELLOW|WARN|SILENT|DEGRADED|QUARANTINE") {
        Write-Host $T -ForegroundColor Yellow -NoNewline
    } else {
        Write-Host $T -ForegroundColor White -NoNewline
    }
}

function Line($Char = "─") {
    Write-Host (($Char) * 120) -ForegroundColor DarkGray
}

while ($true) {
    Clear-Host

    $power  = Get-Api "/system/power"
    $health = Get-Api "/runtime/health"
    $life   = Get-Api "/dashboard/api/v2/system-life"
    $paper  = Get-Api "/dashboard/api/v2/paper"
    $pnl    = Get-Api "/dashboard/api/v2/paper/pnl"
    $brain  = Get-Api "/dashboard/api/v2/brain-dialogue?limit=12"
    $neurons = Get-Api "/dashboard/api/v2/brain-dialogue?component_type=neuron&limit=10"

    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    Write-Host ""
    Write-Host " ██████╗  ██████╗ ██╗  ██╗   ██╗██████╗  ██████╗ ████████╗" -ForegroundColor Cyan
    Write-Host " ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝██╔══██╗██╔═══██╗╚══██╔══╝" -ForegroundColor Cyan
    Write-Host " ██████╔╝██║   ██║██║   ╚████╔╝ ██████╔╝██║   ██║   ██║   " -ForegroundColor Cyan
    Write-Host " ██╔═══╝ ██║   ██║██║    ╚██╔╝  ██╔══██╗██║   ██║   ██║   " -ForegroundColor Cyan
    Write-Host " ██║     ╚██████╔╝███████╗██║   ██████╔╝╚██████╔╝   ██║   " -ForegroundColor Cyan
    Write-Host " ╚═╝      ╚═════╝ ╚══════╝╚═╝   ╚═════╝  ╚═════╝    ╚═╝   " -ForegroundColor Cyan
    Write-Host ""
    Write-Host " LIVE TERMINAL  |  $now  |  refresh: ${RefreshSeconds}s" -ForegroundColor DarkCyan
    Line

    Write-Host "SYSTEM  " -ForegroundColor White -NoNewline
    Badge (Val $power @("power","system_power"))
    Write-Host "   Runtime: " -NoNewline
    Badge (Val $health @("status","runtime_health","health"))
    Write-Host "   MockData: " -NoNewline
    Badge (Val $paper @("mock_data"))
    Write-Host "   Latest Cycle: " -NoNewline
    Write-Host (Val $paper.latest_runtime @("latest_cycle_at","latest_cycle_timestamp")) -ForegroundColor Gray

    Write-Host "SAFETY  " -ForegroundColor White -NoNewline
    Write-Host "LiveOrders=" -NoNewline; Badge (Val $paper @("live_orders"))
    Write-Host "   RealOrders=" -NoNewline; Badge (Val $paper @("real_orders_current","real_orders"))
    Write-Host "   OrdersV2=" -NoNewline; Write-Host (Val $paper @("orders_v2")) -ForegroundColor Gray -NoNewline
    Write-Host "   FillsV2=" -NoNewline; Write-Host (Val $paper @("fills_v2")) -ForegroundColor Gray -NoNewline
    Write-Host "   CanonicalPositions=" -NoNewline; Write-Host (Val $paper @("canonical_positions")) -ForegroundColor Gray

    Write-Host "LINEAGE " -ForegroundColor White -NoNewline
    Write-Host "Status=" -NoNewline; Badge (Val $paper @("paper_lineage_consistency_status","paper_lineage_readiness_status"))
    Write-Host "   Quarantine=" -NoNewline; Badge (Val $paper @("quarantined_paper_positions_count"))
    Write-Host "   ActiveNoFill=" -NoNewline; Badge (Val $paper @("positions_without_fills_count"))
    Write-Host "   RawNoFill=" -NoNewline; Badge (Val $paper @("raw_positions_without_fills_count"))
    Write-Host "   Readiness=" -NoNewline; Badge (Val $paper @("readiness_status"))

    Line

    Write-Host "PAPER STATUS" -ForegroundColor Yellow
    [PSCustomObject]@{
        Intents       = Val $paper @("paper_intents_total","paper_intents")
        Orders        = Val $paper @("paper_orders_total","paper_orders")
        Fills         = Val $paper @("paper_fills_total","paper_fills")
        Positions     = Val $paper @("paper_positions_total","paper_positions")
        Open          = Val $paper @("open_paper_positions")
        Closed        = Val $paper @("closed_paper_positions")
        Closes        = Val $paper @("paper_position_closes")
        Ledger        = Val $paper @("paper_trade_ledger")
        DailyPnLRows  = Val $paper @("paper_daily_pnl")
        RealizedPnL   = Val $paper @("realized_pnl")
        UnrealizedPnL = Val $paper @("unrealized_pnl")
    } | Format-Table -AutoSize

    Line

    Write-Host "NEURON WALL" -ForegroundColor Green

    if ($life -and $life.neuron_coverage) {
        $nc = $life.neuron_coverage
        Write-Host ("Speaking: {0}   Silent: {1}   Missing: {2}   Disabled: {3}" -f `
            (Val $nc @("speaking","neuron_components_speaking")), `
            (Val $nc @("silent","neuron_components_silent")), `
            (Val $nc @("missing","neuron_components_missing")), `
            (Val $nc @("disabled","neuron_components_disabled"))) -ForegroundColor Gray
    } else {
        Write-Host "Neuron coverage summary not found in system-life response." -ForegroundColor DarkYellow
    }

    if ($neurons -and $neurons.events) {
        $neurons.events |
            Select-Object -First 10 timestamp, component, status, human_message |
            Format-Table -Wrap
    } else {
        Write-Host "No neuron dialogue events returned." -ForegroundColor DarkYellow
    }

    Line

    Write-Host "BRAIN DIALOGUE LIVE FEED" -ForegroundColor Cyan

    if ($brain -and $brain.events) {
        $brain.events |
            Select-Object -First 12 timestamp, component, component_type, status, human_message |
            Format-Table -Wrap
    } else {
        Write-Host "No brain dialogue events returned." -ForegroundColor DarkYellow
    }

    Line

    Write-Host "Press CTRL+C to stop." -ForegroundColor DarkGray
    Start-Sleep -Seconds $RefreshSeconds
}
