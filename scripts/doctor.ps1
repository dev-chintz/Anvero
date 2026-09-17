#Requires -Version 5.1

$ErrorActionPreference = "Stop"

Clear-Host

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "        ANVERO DEVELOPMENT DOCTOR" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------
# Git
# ---------------------------------------------------------

Write-Host "Git"

$git = Get-Command git -ErrorAction SilentlyContinue

if ($git) {

    Write-Host "  [OK] Git installed"

    $gitName = git config --global user.name
    $gitEmail = git config --global user.email

    if ($gitName) {
        Write-Host "  [OK] user.name  : $gitName"
    }
    else {
        Write-Host "  [ERROR] user.name not configured" -ForegroundColor Red
    }

    if ($gitEmail) {
        Write-Host "  [OK] user.email : $gitEmail"
    }
    else {
        Write-Host "  [ERROR] user.email not configured" -ForegroundColor Red
    }

}
else {
    Write-Host "  [ERROR] Git not installed" -ForegroundColor Red
}

Write-Host ""

# ---------------------------------------------------------
# Python
# ---------------------------------------------------------

Write-Host "Python"

$python = Get-Command py -ErrorAction SilentlyContinue

if ($python) {

    $version = py --version

    Write-Host "  [OK] $version"

}
else {

    Write-Host "  [ERROR] Python not installed" -ForegroundColor Red

}

Write-Host ""

# ---------------------------------------------------------
# Virtual Environment
# ---------------------------------------------------------

Write-Host "Virtual Environment"

# checking the interpreter rather than the folder: a venv built by the wrong
# Python leaves the folder behind with nothing usable inside
if (Test-Path "backend\.venv\Scripts\python.exe") {

    Write-Host "  [OK] backend\.venv exists"

}
elseif (Test-Path "backend\.venv") {

    Write-Host "  [ERROR] backend\.venv is broken (no Scripts\python.exe); run scripts\bootstrap.ps1 again" -ForegroundColor Red

}
else {

    Write-Host "  [ERROR] backend\.venv not found" -ForegroundColor Red

}

Write-Host ""

# ---------------------------------------------------------
# VS Code
# ---------------------------------------------------------

Write-Host "VS Code"

$code = Get-Command code -ErrorAction SilentlyContinue

if ($code) {

    Write-Host "  [OK] VS Code"

}
else {

    Write-Host "  [ERROR] VS Code command not available" -ForegroundColor Red

}

Write-Host ""

# ---------------------------------------------------------
# Project
# ---------------------------------------------------------

Write-Host "Project"

$folders = @(
    "backend",
    "docs",
    "scripts"
)

foreach ($folder in $folders) {

    if (Test-Path $folder) {

        Write-Host "  [OK] $folder"

    }
    else {

        Write-Host "  [ERROR] Missing $folder" -ForegroundColor Red

    }

}

Write-Host ""

# ---------------------------------------------------------
# GitHub Remote
# ---------------------------------------------------------

Write-Host "Git Remote"

$remote = git remote get-url origin 2>$null

if ($remote) {

    Write-Host "  [OK] $remote"

}
else {

    Write-Host "  [ERROR] origin not configured" -ForegroundColor Red

}

Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Doctor finished." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan