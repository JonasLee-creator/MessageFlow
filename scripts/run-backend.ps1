param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$backendPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'services\backend'
$virtualPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $virtualPython) { $Python = $virtualPython }
Push-Location $backendPath
try {
    & $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
} finally { Pop-Location }
