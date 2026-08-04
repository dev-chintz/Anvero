#Requires -Version 5.1

param(
    
    [Parameter(Position = 0)]
   [ValidateSet("doctor", "bootstrap", "start", "finish", "update", "tests")]
    [string]$Command
)

if (-not $Command) {

    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "           ANVERO COMMANDS" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "bootstrap  - Setup development environment"
    Write-Host "doctor     - Check development environment"
    Write-Host "start      - Start FastAPI backend"
    Write-Host "tests      - Create test structure"
    Write-Host "update     - Update project"
    Write-Host "finish     - Finish development session"

    Write-Host ""
    Write-Host "Example:"
    Write-Host ".\scripts\anvero.ps1 start"
    Write-Host ""

    exit 0
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {

    "doctor" {
        & "$scriptRoot\doctor.ps1"
    }

    "bootstrap" {
        & "$scriptRoot\bootstrap.ps1"
    }

    "start" {
        & "$scriptRoot\start.ps1"
    }

    "finish" {
        & "$scriptRoot\finish.ps1"
    }

    "update" {
        & "$scriptRoot\update.ps1"
    }

    "tests" {
        & "$scriptRoot\create-tests.ps1"
    }
}