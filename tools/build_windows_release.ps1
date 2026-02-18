param(
    [string]$OutDir = "release",
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$releaseRoot = Join-Path $repoRoot $OutDir
$buildDir = Join-Path $releaseRoot "build"
$distDir = Join-Path $releaseRoot "dist"

if (Test-Path $releaseRoot) {
    Remove-Item -Recurse -Force $releaseRoot
}
New-Item -ItemType Directory -Path $buildDir | Out-Null
New-Item -ItemType Directory -Path $distDir | Out-Null

Write-Host "[1/5] Checking PyInstaller..."
$pyi = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyi) {
    throw "PyInstaller not found. Install via: pip install pyinstaller"
}

$oneFileFlag = if ($OneFile) { "--onefile" } else { "" }

Write-Host "[2/5] Building patakha-cli..."
pyinstaller --noconfirm --clean $oneFileFlag --name patakha-cli --distpath $distDir --workpath $buildDir --specpath $buildDir patakha\__main__.py | Out-Host

Write-Host "[3/5] Building patakha-studio..."
pyinstaller --noconfirm --clean $oneFileFlag --windowed --name patakha-studio --distpath $distDir --workpath $buildDir --specpath $buildDir patakha\studio.py | Out-Host

Write-Host "[4/5] Staging runtime bundle..."
$bundleDir = Join-Path $releaseRoot "Patakha-Windows"
New-Item -ItemType Directory -Path $bundleDir | Out-Null

Copy-Item -Recurse -Force (Join-Path $distDir "patakha-cli*") $bundleDir
Copy-Item -Recurse -Force (Join-Path $distDir "patakha-studio*") $bundleDir
Copy-Item -Recurse -Force examples (Join-Path $bundleDir "examples")
Copy-Item -Force README.md (Join-Path $bundleDir "README.md")

$runCli = @"
@echo off
setlocal
if exist "%~dp0\patakha-cli.exe" (
  "%~dp0\patakha-cli.exe" %*
) else (
  "%~dp0\patakha-cli\patakha-cli.exe" %*
)
"@
$runStudio = @"
@echo off
setlocal
if exist "%~dp0\patakha-studio.exe" (
  "%~dp0\patakha-studio.exe"
) else (
  "%~dp0\patakha-studio\patakha-studio.exe"
)
"@
$runCli | Set-Content (Join-Path $bundleDir "run_patakha.bat") -Encoding Ascii
$runStudio | Set-Content (Join-Path $bundleDir "run_studio.bat") -Encoding Ascii

Write-Host "[5/5] Creating zip..."
$zipPath = Join-Path $releaseRoot "Patakha-Windows.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path "$bundleDir\*" -DestinationPath $zipPath -Force

Write-Host "[extra] Optional installer build (Inno Setup)..."
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    $issPath = Join-Path $repoRoot "tools\patakha_installer.iss"
    & $iscc.Source "/DMySource=$bundleDir" $issPath | Out-Host
    Write-Host "[ok] Inno Setup installer generated under $releaseRoot"
}
else {
    Write-Host "[info] iscc not found; skipped installer build. Install Inno Setup for .exe installer output."
}

Write-Host "[ok] Release bundle: $bundleDir"
Write-Host "[ok] Zip package: $zipPath"
