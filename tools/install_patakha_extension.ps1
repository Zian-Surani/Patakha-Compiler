param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$extDir = Join-Path $repoRoot "tools\vscode-patakha-language"

if (-not (Test-Path $extDir)) {
    throw "Extension directory not found: $extDir"
}

Push-Location $extDir
try {
    Write-Host "[1/3] Packaging VS Code extension..."
    npx --yes @vscode/vsce package | Out-Host

    $vsix = Get-ChildItem -Filter "*.vsix" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $vsix) {
        throw "Failed to produce .vsix package."
    }

    Write-Host "[2/3] Installing extension into VS Code..."
    $installArgs = @("--install-extension", $vsix.FullName)
    if ($Force) { $installArgs += "--force" }
    code @installArgs | Out-Host

    Write-Host "[3/3] Done."
    Write-Host "If colors do not appear, run: Developer: Reload Window"
}
finally {
    Pop-Location
}

