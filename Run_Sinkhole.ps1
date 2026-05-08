param(
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"

function Get-BackendDir {
    param([string]$RootDir)

    $candidates = @(
        (Join-Path $RootDir "Project\backend"),
        (Join-Path $RootDir "project\backend")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Test-AppPython {
    param([string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $false
    }

    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process `
            -FilePath $PythonPath `
            -ArgumentList '-c "import fastapi,uvicorn,dotenv"' `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -Wait `
            -PassThru
        return $process.ExitCode -eq 0
    } catch {
        return $false
    } finally {
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Get-AppPython {
    param(
        [string]$RootDir,
        [string]$BackendDir
    )

    $candidates = @(
        (Join-Path $BackendDir ".venv\Scripts\python.exe"),
        (Join-Path $RootDir ".venv-1\Scripts\python.exe"),
        (Join-Path $RootDir ".venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-AppPython -PythonPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Test-ServerReady {
    param([string]$HealthUrl)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-ServerReady {
    param(
        [string]$HealthUrl,
        [System.Diagnostics.Process]$Process,
        [string]$ErrorLog
    )

    for ($i = 0; $i -lt 60; $i++) {
        if ($Process.HasExited) {
            Write-Host "[ERROR] Server process exited before it became ready." -ForegroundColor Red
            if (Test-Path -LiteralPath $ErrorLog) {
                Get-Content -LiteralPath $ErrorLog -Tail 40
            }
            return $false
        }

        if (Test-ServerReady -HealthUrl $HealthUrl) {
            return $true
        }

        Start-Sleep -Milliseconds 500
    }

    Write-Host "[ERROR] Server did not become ready within 30 seconds." -ForegroundColor Red
    if (Test-Path -LiteralPath $ErrorLog) {
        Get-Content -LiteralPath $ErrorLog -Tail 40
    }
    return $false
}

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Get-BackendDir -RootDir $rootDir

if (-not $backendDir) {
    Write-Host "[ERROR] backend directory not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$venvPython = Get-AppPython -RootDir $rootDir -BackendDir $backendDir
if (-not $venvPython) {
    Write-Host "[ERROR] Python environment with FastAPI/Uvicorn was not found." -ForegroundColor Red
    Write-Host "[ERROR] Run Install_Sinkhole.cmd first, or install packages in an existing virtual environment." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location -LiteralPath $backendDir

$hostName = "127.0.0.1"
$port = 5000
$url = "http://${hostName}:${port}/"
$healthUrl = "http://${hostName}:${port}/api/health"
if ($NoRun) {
    Write-Host "[INFO] Run validation completed."
    Write-Host "[INFO] Backend directory: $backendDir"
    Write-Host "[INFO] Python: $venvPython"
    exit 0
}

if (Test-ServerReady -HealthUrl $healthUrl) {
    Write-Host "[INFO] Sinkhole server is already running."
    Write-Host "[INFO] URL: $url"
    Start-Process $url | Out-Null
    exit 0
}

$logDir = Join-Path $backendDir "data\tmp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "launcher.out.log"
$errLog = Join-Path $logDir "launcher.err.log"

$env:SINKHOLE_RELOAD = "0"

Write-Host "[INFO] Starting Sinkhole server..."
Write-Host "[INFO] URL: $url"
Write-Host "[INFO] Python: $venvPython"
Write-Host "[INFO] Logs: $outLog"

$serverProcess = Start-Process `
    -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", $hostName, "--port", "$port", "--log-level", "info") `
    -WorkingDirectory $backendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

if (-not (Wait-ServerReady -HealthUrl $healthUrl -Process $serverProcess -ErrorLog $errLog)) {
    if (-not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[INFO] Server is ready."
Start-Process $url | Out-Null
Write-Host "[INFO] Browser opened. Keep this window open while using the app."
Write-Host "[INFO] Close this window or press Ctrl+C to stop the server."

try {
    while (-not $serverProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "[INFO] Server stopped."
