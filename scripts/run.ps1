param([switch]$ExternalDatabase, [string]$ListenAddress = '127.0.0.1')
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '..\..'))
$sharedRoot = if (Test-Path -LiteralPath (Join-Path $workspaceRoot 'backend\main.py')) { $workspaceRoot } else { $repositoryRoot }
Set-Location -LiteralPath $sharedRoot
$alreadyRunning = $false
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
    $alreadyRunning = $health.status -eq 'ok' -and $health.database -eq 'postgresql'
} catch { }
if ($alreadyRunning) {
    $schema = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 2
    if (-not $schema.paths.PSObject.Properties['/adoption/listings'] -or -not $schema.paths.PSObject.Properties['/shop/products']) {
        throw 'The common backend is running older code. Stop that instance, then rerun this script to apply migrations and restart it.'
    }
    Write-Host 'Common backend is already running. React JS: http://127.0.0.1:8000/app'
    return
}
if (-not $ExternalDatabase) {
    & '.\.venv\Scripts\python.exe' -m scripts.local_db
    if ($LASTEXITCODE -ne 0) { throw 'Database startup failed' }
}
& '.\.venv\Scripts\python.exe' -m scripts.init_db --schema-only
if ($LASTEXITCODE -ne 0) { throw 'Common database migration failed' }
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host $ListenAddress --port 8000
