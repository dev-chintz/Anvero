#Requires -Version 5.1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "      ANVERO TEST STRUCTURE SETUP" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot

$directories = @(
    "backend/tests",
    "backend/tests/api",
    "backend/tests/db",
    "backend/tests/models",
    "backend/tests/services"
)

foreach ($dir in $directories) {

    $path = Join-Path $projectRoot $dir

    if (!(Test-Path $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
        Write-Host "[OK] Created $dir" -ForegroundColor Green
    }
    else {
        Write-Host "[SKIP] $dir already exists" -ForegroundColor Yellow
    }
}

$files = @(
    "backend/tests/__init__.py",
    "backend/tests/conftest.py",
    "backend/tests/api/__init__.py",
    "backend/tests/db/__init__.py",
    "backend/tests/models/__init__.py",
    "backend/tests/services/__init__.py"
)

foreach ($file in $files) {

    $path = Join-Path $projectRoot $file

    if (!(Test-Path $path)) {
        New-Item -ItemType File -Path $path | Out-Null
        Write-Host "[OK] Created $file" -ForegroundColor Green
    }
    else {
        Write-Host "[SKIP] $file already exists" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Test structure ready." -ForegroundColor Green