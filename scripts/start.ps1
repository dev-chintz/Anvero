#Requires -Version 5.1

$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot\..\backend"

if (!(Test-Path ".venv")) {
    Write-Host "[ERROR] Virtual environment not found." -ForegroundColor Red
    exit 1
}

& ".\.venv\Scripts\Activate.ps1"

Write-Host ""
Write-Host "Starting Anvero API..."
Write-Host ""

python -m uvicorn app.main:app --reload