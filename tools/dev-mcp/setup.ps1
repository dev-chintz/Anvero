#Requires -Version 5.1
<#
.SYNOPSIS
    Sets up the venv for Anvero's dev-loop MCP server (tools/dev-mcp).

.DESCRIPTION
    One-time per machine. Creates tools/dev-mcp/.venv and installs
    requirements.txt into it. The repo's .mcp.json points an MCP client
    (Claude Code, and any other client reading that file) at this venv's
    python running server.py, so running this is what makes the
    `restart_backend` / `sync_test_counts` tools available.

    Mirrors scripts/bootstrap.ps1's Python discovery: the first `python` on
    PATH is not necessarily a usable CPython (see CLAUDE.md), so the `py`
    launcher is preferred.
#>

$ErrorActionPreference = "Stop"
$toolPath = $PSScriptRoot
$venvPath = Join-Path $toolPath ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

Write-Host "Setting up the dev-mcp venv ..." -ForegroundColor Cyan

$pythonExe = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
}
else {
    Write-Host "[ERROR] No Python found on PATH." -ForegroundColor Red
    exit 1
}

if (!(Test-Path $venvPython)) {
    & $pythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0 -or !(Test-Path $venvPython)) {
        Write-Host "[ERROR] Failed to create the virtual environment." -ForegroundColor Red
        Write-Host "        If $pythonExe resolved to a non-standard Python (see CLAUDE.md's" -ForegroundColor Red
        Write-Host "        'first python on PATH' gotcha), install CPython from python.org." -ForegroundColor Red
        exit 1
    }
}

& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $toolPath "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install requirements." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Ready: $venvPython" -ForegroundColor Green
Write-Host "Restart your MCP client (e.g. Claude Code) so it picks up .mcp.json."
