$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$limit = if ($args.Count -gt 0) { $args[0] } else { "50" }

Push-Location $repoRoot
try {
    $python = @"
from app.services.rules_resolution_truth import RulesResolutionTruthService

result = RulesResolutionTruthService().refresh_rules_truth(limit=int("$limit"), allow_ai=False)
print("status=", result.get("status"))
print("selected_market_families=", ",".join(result.get("selected_market_families") or []))
print("candidate_count=", result.get("candidate_count"))
print("refreshed_rules=", result.get("refreshed_rules"))
print("analyzed=", result.get("analyzed"))
print("failed=", result.get("failed"))
"@
    $python | docker compose exec -T api python -
}
finally {
    Pop-Location
}
