$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $projectRoot "frontend\RA-Project"
$backendDir = Join-Path $projectRoot "backend"
$venvDir = Join-Path $backendDir ".venv-packager"
$frontendDist = Join-Path $frontendDir "dist"
$backendFrontendDist = Join-Path $backendDir "frontend_dist"
$releaseDir = Join-Path $projectRoot "release"
$pyInstallerDist = Join-Path $backendDir "dist\RA Launcher"
$releaseZip = Join-Path $releaseDir "RA-Launcher-windows.zip"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )
    Write-Host $Label
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Building frontend..."
Push-Location $frontendDir
& npm ci
if ($LASTEXITCODE -ne 0) {
    Write-Host "npm ci failed; retrying with npm install..."
    & npm install
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency install failed."
    }
}
Invoke-Step "Running frontend build..." { npm run build }
Pop-Location

if (-Not (Test-Path $frontendDist)) {
    throw "Frontend build output not found at $frontendDist"
}

Write-Host "Preparing backend static assets..."
if (Test-Path $backendFrontendDist) {
    Remove-Item $backendFrontendDist -Recurse -Force
}
Copy-Item $frontendDist $backendFrontendDist -Recurse

Write-Host "Creating Python packaging environment..."
if (-Not (Test-Path $venvDir)) {
    Invoke-Step "Creating Python venv..." { python -m venv $venvDir }
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"

Invoke-Step "Upgrading pip..." { & $venvPython -m pip install --upgrade pip }
Invoke-Step "Installing Python dependencies..." { & $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt") pyinstaller }

Write-Host "Building launcher executable..."
Push-Location $backendDir
Invoke-Step "Running PyInstaller..." { & $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --name "RA Launcher" `
    --console `
    --add-data "frontend_dist;frontend_dist" `
    launcher.py
}
Pop-Location

if (-Not (Test-Path $pyInstallerDist)) {
    throw "PyInstaller output folder not found at $pyInstallerDist"
}

Write-Host "Preparing release folder..."
if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
}
New-Item -Path $releaseDir -ItemType Directory | Out-Null

Copy-Item $pyInstallerDist (Join-Path $releaseDir "RA-Launcher") -Recurse
Copy-Item (Join-Path $projectRoot "PACKAGE_GUIDE.md") (Join-Path $releaseDir "PACKAGE_GUIDE.md")

Write-Host "Creating release zip..."
if (Test-Path $releaseZip) {
    Remove-Item $releaseZip -Force
}
Compress-Archive -Path (Join-Path $releaseDir "RA-Launcher\*") -DestinationPath $releaseZip -Force

Write-Host ""
Write-Host "Done. Distributable files are in:"
Write-Host "  $releaseDir"
Write-Host ""
Write-Host "Share '$releaseZip' for Windows users."
