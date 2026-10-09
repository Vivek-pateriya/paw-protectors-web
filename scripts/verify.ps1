$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
& '.\.venv\Scripts\python.exe' -m scripts.verify
if ($LASTEXITCODE -ne 0) { throw 'Verification failed; see artifacts' }
