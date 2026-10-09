$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolRoot = Join-Path $projectRoot '.tools'
New-Item -ItemType Directory -Force $toolRoot | Out-Null
$archive = Join-Path $toolRoot 'postgresql.zip'
if (-not (Test-Path (Join-Path $toolRoot 'pgsql\bin\pg_ctl.exe'))) {
    Invoke-WebRequest 'https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip' -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $toolRoot -Force
}
Write-Output "PostgreSQL binaries: $toolRoot\pgsql\bin"
