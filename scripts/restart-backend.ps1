#Requires -Version 5.1
<#
.SYNOPSIS
    Cleanly restarts the FastAPI backend on Windows.

.DESCRIPTION
    CLAUDE.md documents a recurring trap: `uvicorn --reload` runs two
    processes, and killing only the parent leaves the worker alive, still
    holding the port and answering with the code it started with. A new
    server then binds nothing, or the old one keeps answering, and a code
    change looks like it did nothing.

    This script finds and stops everything on the port (the listener and any
    orphaned `python.exe` whose command line contains `multiprocessing.spawn`
    for this app), starts a fresh server in the background, and waits for
    `/api/v1/health` to answer before returning - so "it's running" is
    checked, not assumed.

.PARAMETER Port
    The port to free and start the server on. Default 8000.

.PARAMETER Reload
    Start with `--reload` (auto-restart on file changes). Off by default:
    every reload-triggered restart risks the same orphan-worker trap this
    script exists to clean up after. Use it for a short edit session, and
    run this script again without it if a reload leaves the port stuck.

.EXAMPLE
    .\scripts\restart-backend.ps1
.EXAMPLE
    .\scripts\restart-backend.ps1 -Reload
#>

param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$backendPath = Join-Path $PSScriptRoot "..\backend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"

if (!(Test-Path $venvPython)) {
    Write-Host "[ERROR] $venvPython not found. Run bootstrap first." -ForegroundColor Red
    exit 1
}

Write-Host "Stopping anything on port $Port ..." -ForegroundColor Cyan

# The listener(s) currently bound to the port.
$listenerPids = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)

# Orphaned reload workers: no longer listening, but still this app's process.
# Get-Process has no command line, so Win32_Process is used instead.
$orphanPids = @(
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*multiprocessing.spawn*" -and
            $_.CommandLine -like "*app.main*"
        } |
        Select-Object -ExpandProperty ProcessId
)

$toStop = @($listenerPids + $orphanPids | Select-Object -Unique)

if ($toStop.Count -eq 0) {
    Write-Host "Nothing was listening on port $Port." -ForegroundColor Yellow
}
else {
    foreach ($stopPid in $toStop) {
        try {
            # the tree, not just the parent: this is exactly the orphan trap
            Stop-Process -Id $stopPid -Force -ErrorAction Stop
            Write-Host "  stopped PID $stopPid" -ForegroundColor DarkGray
        }
        catch {
            Write-Host "  could not stop PID ${stopPid}: $_" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 1
}

$stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($stillListening) {
    Write-Host "[ERROR] Port $Port is still held by PID(s) $($stillListening.OwningProcess -join ', ')." -ForegroundColor Red
    Write-Host "Stop it by hand and re-run this script." -ForegroundColor Red
    exit 1
}

Write-Host "Starting the backend on port $Port ..." -ForegroundColor Cyan

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

$logFile = Join-Path $env:TEMP "anvero-backend-$Port.log"
$process = Start-Process -FilePath $venvPython -ArgumentList $uvicornArgs `
    -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"

Write-Host "Started PID $($process.Id); log: $logFile"

$healthUrl = "http://127.0.0.1:$Port/api/v1/health"
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($response.status -eq "ok") {
            $ready = $true
            break
        }
    }
    catch {
        # not up yet, or still migrating (alembic runs first); keep polling
    }
}

if ($ready) {
    Write-Host "[OK] Healthy: $healthUrl" -ForegroundColor Green
    Write-Host "To confirm which code is actually running: GET http://127.0.0.1:$Port/openapi.json"
    Write-Host "To stop it: Stop-Process -Id $($process.Id)"
}
else {
    Write-Host "[ERROR] Did not become healthy in time. Check the log:" -ForegroundColor Red
    Write-Host "  $logFile"
    Write-Host "  $logFile.err"
    exit 1
}
