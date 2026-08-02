# Builds the Windows MSI installer (cx_Freeze) using the local venv_win environment.
$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "venv_win\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Could not find virtual environment python at '$python'." -ForegroundColor Red
    Write-Host "Create it with: python -m venv package_win\venv_win"
    exit 1
}

# setup.py lives here and anchors its source paths to the project root, so run the
# build from this folder -- that way build/ and dist/ land under package_win/,
# keeping the repo root clean.
Set-Location -Path $PSScriptRoot
& $python "setup.py" "bdist_msi"
exit $LASTEXITCODE
