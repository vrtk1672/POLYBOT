$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8000"
$paths = @(
    "/docs",
    "/openapi.json",
    "/dashboard",
    "/dashboard/api/health",
    "/dashboard/api/overview"
)

foreach ($path in $paths) {
    $response = Invoke-WebRequest ($base + $path) -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
        throw "Smoke check failed for $path with status $($response.StatusCode)"
    }
    Write-Output "$path OK"
}
