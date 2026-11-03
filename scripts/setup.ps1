param([string]$Python = 'python', [switch]$ExternalDatabase)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '..\..'))
$serverRoot = if (Test-Path -LiteralPath (Join-Path $workspaceRoot 'backend\main.py')) { $workspaceRoot } else { $repositoryRoot }
Set-Location -LiteralPath $serverRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r backend/requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
New-Item -ItemType Directory -Force artifacts | Out-Null
if (-not $ExternalDatabase) {
    & '.\.venv\Scripts\python.exe' -m scripts.download_postgres
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL download failed' }
    & '.\.venv\Scripts\python.exe' -m scripts.local_db
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed' }
} elseif (-not (Test-Path '.env')) { throw 'Configure .env for your external PostgreSQL server first.' }
& '.\.venv\Scripts\python.exe' -m scripts.init_db
if ($LASTEXITCODE -ne 0) { throw 'Schema initialization failed' }
