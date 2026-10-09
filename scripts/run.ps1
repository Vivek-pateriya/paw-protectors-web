param([switch]$ExternalDatabase)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not $ExternalDatabase) {
    & '.\.venv\Scripts\python.exe' -m scripts.local_db
    if ($LASTEXITCODE -ne 0) { throw 'Database startup failed' }
}
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
