#Requires -Version 5.1
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "====================================="
Write-Host "   Anvero - Project Bootstrap"
Write-Host "====================================="
Write-Host ""

$directories = @(
    "backend/app/api",
    "backend/app/api/v1",
    "backend/app/api/v1/endpoints",
    "backend/app/core",
    "backend/app/db",
    "backend/app/models",
    "backend/app/repositories",
    "backend/app/schemas",
    "backend/app/services",
    "backend/app/utils"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "[OK] Created $dir"
    }
    else {
        Write-Host "[SKIP] $dir already exists"
    }
}

$initFiles = @(
    "backend/app/api/__init__.py",
    "backend/app/api/v1/__init__.py",
    "backend/app/api/v1/endpoints/__init__.py",
    "backend/app/core/__init__.py",
    "backend/app/db/__init__.py",
    "backend/app/models/__init__.py",
    "backend/app/repositories/__init__.py",
    "backend/app/schemas/__init__.py",
    "backend/app/services/__init__.py",
    "backend/app/utils/__init__.py"
)

foreach ($file in $initFiles) {
    if (!(Test-Path $file)) {
        New-Item -ItemType File -Path $file | Out-Null
        Write-Host "[OK] Created $file"
    }
    else {
        Write-Host "[SKIP] $file already exists"
    }
}

Write-Host ""
Write-Host "Project structure is ready."