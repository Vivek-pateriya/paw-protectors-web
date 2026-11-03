$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '..\..'))
if (Test-Path -LiteralPath (Join-Path $workspaceRoot 'backend\main.py')) { $projectRoot = $workspaceRoot }
& (Join-Path $projectRoot '.tools\pgsql\bin\pg_ctl.exe') -D (Join-Path $projectRoot '.pgdata') -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw 'Database shutdown failed' }
