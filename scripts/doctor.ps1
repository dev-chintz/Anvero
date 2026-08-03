[CmdletBinding()]
param()

$projectRoot = Split-Path -Parent $PSScriptRoot
$failures = 0
$warnings = 0

function Test-Requirement {
  param([string]$Name, [string]$Command, [bool]$Required = $true)

  $available = Get-Command $Command -ErrorAction SilentlyContinue
  if ($available) {
    Write-Host "[OK] ${Name}: $($available.Source)" -ForegroundColor Green
  } elseif ($Required) {
    Write-Host "[ERROR] Missing: $Name" -ForegroundColor Red
    $script:failures++
  } else {
    Write-Host "[INFO] Optional and not installed yet: $Name" -ForegroundColor Yellow
    $script:warnings++
  }
}

Write-Host 'Anvero doctor'
Write-Host "Project: $projectRoot"

Test-Requirement -Name 'Git' -Command 'git'
$python = Get-Command python -ErrorAction SilentlyContinue
$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($python -or $pythonLauncher) {
  $pythonCommand = if ($python) { $python } else { $pythonLauncher }
  $pythonArguments = if ($python) { @() } else { @('-3') }
  $pythonVersionCode = [int](& $pythonCommand.Source @pythonArguments -c 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])')
  $pythonVersion = "$([math]::Floor($pythonVersionCode / 100)).$($pythonVersionCode % 100)"
  if ($pythonVersionCode -lt 311) {
    Write-Host "[ERROR] Python $pythonVersion found; Anvero requires Python 3.11+." -ForegroundColor Red
    $failures++
  } else {
    Write-Host "[OK] Python ${pythonVersion}: $($pythonCommand.Source)" -ForegroundColor Green
  }
} else {
  Write-Host '[ERROR] Missing: Python 3.11+' -ForegroundColor Red
  $failures++
}
Test-Requirement -Name 'Node.js (wymagany od frontendu)' -Command 'node' -Required $false
Test-Requirement -Name 'PostgreSQL / psql (wymagany od Sprintu 2)' -Command 'psql' -Required $false

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  $venvVersionCode = [int](& $venvPython -c 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])')
  $venvVersion = "$([math]::Floor($venvVersionCode / 100)).$($venvVersionCode % 100)"
  if ($venvVersionCode -lt 311) {
    Write-Host "[ERROR] Local Python $venvVersion found; recreate .venv with Python 3.11+." -ForegroundColor Red
    $failures++
  } else {
    Write-Host "[OK] Local Python environment ${venvVersion}: $venvPython" -ForegroundColor Green
  }
} else {
  Write-Host '[ERROR] .venv is missing. Run .\scripts\bootstrap.ps1.' -ForegroundColor Red
  $failures++
}

foreach ($path in @('backend', 'frontend', 'database', 'docs', 'scripts')) {
  if (Test-Path (Join-Path $projectRoot $path)) {
    Write-Host "[OK] Katalog: $path" -ForegroundColor Green
  } else {
    Write-Host "[ERROR] Missing directory: $path" -ForegroundColor Red
    $failures++
  }
}

if ($failures -gt 0) {
  Write-Host "Doctor finished: $failures errors, $warnings notes." -ForegroundColor Red
  exit 1
}

Write-Host "Environment is ready. Additional notes: $warnings." -ForegroundColor Green
