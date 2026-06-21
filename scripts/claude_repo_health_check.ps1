# POLYBOT Claude Repo Health Check
# Safe read-only check. Does not print secrets.

Write-Host "POLYBOT Claude Repo Health Check" -ForegroundColor Cyan
Write-Host "Location: $(Get-Location)" -ForegroundColor Cyan

$checks = @(
    "CLAUDE.md",
    "AGENTS.md",
    "docs",
    "docs\POLYBOT_CLAUDE_WORKFLOW.md",
    "docs\POLYBOT_PROMPT_OPERATING_SYSTEM.md",
    "docs\POLYBOT_SAFETY_RULES.md",
    ".claude",
    ".claude\skills",
    ".claude\skills\polybot-output-reviewer\SKILL.md",
    ".claude\skills\polybot-phase-builder\SKILL.md",
    ".claude\skills\polybot-safety-auditor\SKILL.md",
    ".claude\skills\polybot-current-reality-auditor\SKILL.md",
    ".claude\skills\polybot-test-runner\SKILL.md"
)

foreach ($item in $checks) {
    if (Test-Path $item) {
        Write-Host "[OK] $item" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $item" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Git status:" -ForegroundColor Cyan
git status --short

Write-Host ""
Write-Host "Secret files presence only, values are not printed:" -ForegroundColor Cyan
$secretFiles = @(".env", ".env.local", ".env.production")
foreach ($file in $secretFiles) {
    if (Test-Path $file) {
        Write-Host "[PRESENT] $file" -ForegroundColor Yellow
    } else {
        Write-Host "[OK missing] $file" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
