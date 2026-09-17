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
#
# The first `python` on PATH is not necessarily a usable CPython: other
# programs bundle their own (Inkscape ships a MinGW build whose venvs have no
# Scripts\ directory and no working pip). Each candidate is therefore asked
# whether it is new enough and lays a venv out the Windows way, and the py
# launcher is tried first because it resolves to a real CPython install.

$venvProbe = "import sys, sysconfig; " +
    "ok = sys.version_info >= (3, 11) and " +
    "sysconfig.get_path('scripts').rstrip('\\/').lower().endswith('scripts'); " +
    "print(sys.executable if ok else '')"

$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += , @("py", "-3")
}
foreach ($cmd in (Get-Command python -All -ErrorAction SilentlyContinue)) {
    $candidates += , @($cmd.Source)
}

$pythonExe = $null
foreach ($candidate in $candidates) {
    $exe = $candidate[0]
    $prefix = @($candidate | Select-Object -Skip 1)
    try {
        $resolved = & $exe @prefix -c $venvProbe 2>$null
    }
    catch {
        continue
    }
    if ($LASTEXITCODE -eq 0 -and $resolved) {
        $pythonExe = "$resolved".Trim()
        break
    }
}

if (-not $pythonExe) {
    Write-Host "[ERROR] No usable Python 3.11+ found." -ForegroundColor Red
    Write-Host "        Install CPython from python.org; a Python bundled with another" -ForegroundColor Red
    Write-Host "        program (e.g. Inkscape) cannot build this project's venv." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python found: $pythonExe" -ForegroundColor Green

# Virtual environment

$venvPython = Join-Path $venvPath "Scripts\python.exe"

if ((Test-Path $venvPath) -and !(Test-Path $venvPython)) {
    # left behind by an earlier run with an unusable interpreter; it can never
    # work, and `venv` will not repair it in place
    Write-Host "[INFO] Removing broken virtual environment at $venvPath" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

if (!(Test-Path $venvPython)) {

    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow

    & $pythonExe -m venv $venvPath

    if ($LASTEXITCODE -ne 0 -or !(Test-Path $venvPython)) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

Write-Host "[OK] Virtual environment ready." -ForegroundColor Green

# Dependencies

$requirements = Join-Path $backendPath "requirements.txt"

if (!$SkipDependencies) {

    if (Test-Path $requirements) {

        Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow

        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to upgrade pip." -ForegroundColor Red
            exit 1
        }

        & $venvPython -m pip install -r $requirements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to install dependencies." -ForegroundColor Red
            exit 1
        }

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