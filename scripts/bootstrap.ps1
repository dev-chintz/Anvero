#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "      ANVERO ENVIRONMENT BOOTSTRAP" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$venvPath = Join-Path $backendPath ".venv"

# Python
$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $python) {
    Write-Host "[ERROR] Python not found." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python found." -ForegroundColor Green

# Virtual environment

if (!(Test-Path "$venvPath\Scripts\python.exe")) {

    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow

    if ($python.Name -eq "py.exe" -or $python.Name -eq "py") {
        & $python.Source -3 -m venv $venvPath
    }
    else {
        & $python.Source -m venv $venvPath
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

Write-Host "[OK] Virtual environment ready." -ForegroundColor Green

$venvPython = Join-Path $venvPath "Scripts\python.exe"

# Dependencies

$requirements = Join-Path $backendPath "requirements.txt"

if (!$SkipDependencies) {

    if (Test-Path $requirements) {

        Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow

        & $venvPython -m pip install --upgrade pip

        & $venvPython -m pip install -r $requirements

        Write-Host "[OK] Dependencies installed." -ForegroundColor Green

    }
    else {

        Write-Host "[WARNING] requirements.txt not found." -ForegroundColor Yellow

    }
}

# .env

$envFile = Join-Path $backendPath ".env"
$envExample = Join-Path $backendPath ".env.example"

if (!(Test-Path $envFile) -and (Test-Path $envExample)) {

    Copy-Item $envExample $envFile

    Write-Host "[OK] .env created from .env.example" -ForegroundColor Green

}

Write-Host ""
Write-Host "Bootstrap completed successfully." -ForegroundColor Green