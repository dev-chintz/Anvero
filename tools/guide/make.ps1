# Makes the guide's screenshots (docs/GUIDE.md): seeds an invented shop into a scratch database, starts
# the backend and the interface on it, takes the pictures with Chrome and stops everything again.
# Nothing here touches the real database; the pictures go to frontend/public/guide.
#
#   .\tools\guide\make.ps1            all of them
#   .\tools\guide\make.ps1 -Only dashboard,orders
param([string[]]$Only = @())

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "backend\.venv not found: run scripts\bootstrap.ps1" }

foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is in use: stop the running backend or interface first (it would be shown instead of the sample shop)."
    }
}

function Wait-Until([string]$Url, [int]$Seconds = 60) {
    $until = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $until) {
        try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null; return } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "$Url did not come up"
}

$backend = $null
$frontend = $null
try {
    & $python (Join-Path $PSScriptRoot "seed_sample.py")
    if ($LASTEXITCODE -ne 0) { throw "the sample data could not be made" }

    $backend = Start-Process -FilePath $python -ArgumentList (Join-Path $PSScriptRoot "run_backend.py") -PassThru -WindowStyle Hidden
    Wait-Until "http://127.0.0.1:8000/api/v1/health"

    $frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--prefix", (Join-Path $root "frontend") -PassThru -WindowStyle Hidden
    Wait-Until "http://localhost:5173/"

    $arguments = @((Join-Path $PSScriptRoot "capture.mjs"))
    if ($Only.Count -gt 0) { $arguments += @("--only", ($Only -join ",")) }
    & node @arguments
    if ($LASTEXITCODE -ne 0) { throw "the screenshots could not be taken" }
}
finally {
    foreach ($process in $frontend, $backend) {
        if ($process) { & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null }
    }
}
