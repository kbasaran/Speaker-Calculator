# Runs the application using the local venv_win environment.
$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv_win\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Could not find virtual environment python at '$python'." -ForegroundColor Red
    Write-Host "Create it with: python -m venv package_win\venv_win"
    exit 1
}

# main.py and its data files live in the project root (the parent of this folder),
# and the app resolves data paths relative to the working directory -- run from there.
$root = Split-Path -Parent $PSScriptRoot
Set-Location -Path $root
& $python "main.py" @args
exit $LASTEXITCODE
