[CmdletBinding()]
param(
  [switch]$SkipDependencies
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue

if (-not $pythonCommand) {
  $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCommand) {
  throw 'Python was not found. Install Python 3.11+ and run this script again.'
}

$pythonArguments = @()
if ($pythonCommand.Name -eq 'py.exe' -or $pythonCommand.Name -eq 'py') {
  $pythonArguments += '-3'
}
$pythonVersionCode = [int](& $pythonCommand.Source @pythonArguments -c 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])')
$pythonVersion = "$([math]::Floor($pythonVersionCode / 100)).$($pythonVersionCode % 100)"
if ($pythonVersionCode -lt 311) {
  throw "Python $pythonVersion was found, but Anvero requires Python 3.11+."
}

if (-not (Test-Path (Join-Path $venvPath 'Scripts\python.exe'))) {
  Write-Host 'Creating local Python environment (.venv)...'
  & $pythonCommand.Source @pythonArguments -m venv $venvPath
}

$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$requirements = Join-Path $projectRoot 'backend\requirements\base.txt'
if (-not $SkipDependencies -and (Test-Path $requirements)) {
  Write-Host 'Installing backend dependencies...'
  & $venvPython -m pip install --upgrade pip | Out-Host
  & $venvPython -m pip install -r $requirements | Out-Host
} elseif (-not (Test-Path $requirements)) {
  Write-Host 'backend/requirements/base.txt not found - dependency installation skipped.'
}

Write-Host 'Done. Activate the environment with: .\.venv\Scripts\Activate.ps1'
