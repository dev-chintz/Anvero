#Requires -Version 5.1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "          STARTING ANVERO API" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Przejście do katalogu backend
Set-Location "$PSScriptRoot\..\backend"

# Sprawdzenie virtual environment
if (!(Test-Path ".venv")) {
    Write-Host "[ERROR] Virtual environment not found." -ForegroundColor Red
    Write-Host "Run bootstrap first." -ForegroundColor Yellow
    exit 1
}

# Sprawdzenie pliku .env
if (!(Test-Path ".env")) {
    Write-Host "[WARNING] .env not found." -ForegroundColor Yellow

    if (Test-Path ".env.example") {
        Write-Host "[INFO] You can create it with:" -ForegroundColor Yellow
        Write-Host "Copy-Item .env.example .env"
    }

    Write-Host ""
}

# Aktywacja virtual environment
try {
    & ".\.venv\Scripts\Activate.ps1"
}
catch {
    Write-Host "[ERROR] Failed to activate virtual environment." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Virtual environment activated." -ForegroundColor Green
Write-Host ""
Write-Host "Swagger UI:"
Write-Host "http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "Starting FastAPI..."
Write-Host ""

python -m uvicorn app.main:app --reload