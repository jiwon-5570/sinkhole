$ErrorActionPreference = "Continue"

$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rootDir = (Resolve-Path (Join-Path $backendDir "..\..")).Path
$python = Join-Path $rootDir ".venv-1\Scripts\python.exe"
$log = Join-Path $backendDir "data\tmp\server-persistent.log"

Set-Location $backendDir

$env:SINKHOLE_RELOAD = "0"
$env:SINKHOLE_PUBLIC_DATA_AUTO_COLLECT = "0"
$env:SINKHOLE_PUBLIC_DATA_COLLECT_ON_START = "0"
$env:SINKHOLE_ANALYZE_ON_START = "0"
$env:SINKHOLE_LOCAL_CONSTRUCTION_FILE_IMPORT_ENABLED = "0"

& $python -m uvicorn app.main:app --host 127.0.0.1 --port 5000 --log-level info *>> $log
