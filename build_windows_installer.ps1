$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerScript = Join-Path $projectRoot "installer\RA-Launcher.iss"
$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

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

Invoke-Step "Building app package first..." {
    powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_windows_package.ps1")
}

$isccPath = $null
foreach ($candidate in $isccCandidates) {
    if (Test-Path $candidate) {
        $isccPath = $candidate
        break
    }
}

if (-not $isccPath) {
    try {
        $isccCmd = Get-Command iscc -ErrorAction Stop
        $isccPath = $isccCmd.Source
    } catch {
        throw @"
Inno Setup compiler (ISCC.exe) was not found.

Install Inno Setup 6:
https://jrsoftware.org/isinfo.php

Then run this script again:
  build_windows_installer.bat
"@
    }
}

Invoke-Step "Compiling installer EXE..." {
    & $isccPath $installerScript
}

$installerOut = Join-Path $projectRoot "release\installer\RA-Launcher-Setup.exe"
if (-not (Test-Path $installerOut)) {
    throw "Installer build completed but output was not found at $installerOut"
}

Write-Host ""
Write-Host "Done. Installer created at:"
Write-Host "  $installerOut"
