#Requires -Version 5.1

git pull

Set-Location "$PSScriptRoot\..\backend"

if (Test-Path ".venv") {
    & ".\.venv\Scripts\Activate.ps1"
    python -m pip install -r requirements.txt
}