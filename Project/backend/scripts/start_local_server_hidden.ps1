$ErrorActionPreference = "Stop"

$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rootDir = (Resolve-Path (Join-Path $backendDir "..\..")).Path
$pythonw = Join-Path $rootDir ".venv-1\Scripts\pythonw.exe"
$python = Join-Path $rootDir ".venv-1\Scripts\python.exe"
$outLog = Join-Path $backendDir "data\tmp\server-hidden.out.log"
$errLog = Join-Path $backendDir "data\tmp\server-hidden.err.log"

$env:SINKHOLE_RELOAD = "0"
$env:SINKHOLE_PUBLIC_DATA_AUTO_COLLECT = "0"
$env:SINKHOLE_PUBLIC_DATA_COLLECT_ON_START = "0"
$env:SINKHOLE_ANALYZE_ON_START = "0"

$exe = if (Test-Path -LiteralPath $pythonw) { $pythonw } else { $python }
Start-Process `
    -FilePath $exe `
    -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 5000 --log-level info" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -WindowStyle Hidden
