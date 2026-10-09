$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $projectRoot '.tools\pgsql\bin\pg_ctl.exe') -D (Join-Path $projectRoot '.pgdata') -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw 'Database shutdown failed' }
