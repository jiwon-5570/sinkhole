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

function Get-PythonCommand {
    foreach ($cmd in @("py", "python")) {
        try {
            $null = & $cmd --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $cmd
            }
        } catch {
        }
    }

    return $null
}

function Ensure-Venv {
    param(
        [string]$BackendDir,
        [string]$VenvPython
    )

    if (Test-Path -LiteralPath $VenvPython) {
        return
    }

    $pythonCmd = Get-PythonCommand
    if (-not $pythonCmd) {
        throw "Python 3.11+ was not found."
    }

    Write-Host "[INFO] Creating virtual environment..."
    & $pythonCmd -m venv (Join-Path $BackendDir ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        throw "Failed to create virtual environment."
    }
}

function Ensure-Packages {
    param([string]$VenvPython)

    $pkgCheck = @'
import importlib.util
required = ['fastapi', 'uvicorn', 'dotenv', 'requests', 'reportlab']
missing = [name for name in required if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
'@
    & $VenvPython -c $pkgCheck
    $needsInstall = $LASTEXITCODE -ne 0

    if (-not $needsInstall) {
        return
    }

    Write-Host "[INFO] Installing Python packages..."
    & $VenvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Python packages."
    }
}

function Ensure-Database {
    param([string]$VenvPython)

    Write-Host "[INFO] Initializing database..."
    & $VenvPython .\scripts\init_db.py
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize database."
    }
}

function Create-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory,
        [string]$IconLocation
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    if ($IconLocation) {
        $shortcut.IconLocation = $IconLocation
    }
    $shortcut.Save()
}

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Get-BackendDir -RootDir $rootDir

if (-not $backendDir) {
    Write-Host "[ERROR] backend directory not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location -LiteralPath $backendDir

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"

try {
    Ensure-Venv -BackendDir $backendDir -VenvPython $venvPython
    Ensure-Packages -VenvPython $venvPython
    Ensure-Database -VenvPython $venvPython

    $runCmd = Join-Path $rootDir "Run_Sinkhole.cmd"
    $rootShortcut = Join-Path $rootDir "Sinkhole Launcher.lnk"
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Sinkhole Launcher.lnk"
    $icon = "$env:SystemRoot\System32\shell32.dll,220"

    Create-Shortcut -ShortcutPath $rootShortcut -TargetPath $runCmd -WorkingDirectory $rootDir -IconLocation $icon
    Create-Shortcut -ShortcutPath $desktopShortcut -TargetPath $runCmd -WorkingDirectory $rootDir -IconLocation $icon

    Write-Host "[INFO] Installation completed."
    Write-Host "[INFO] Root shortcut: $rootShortcut"
    Write-Host "[INFO] Desktop shortcut: $desktopShortcut"

    if ($NoRun) {
        exit 0
    }

    Write-Host "[INFO] Launching application..."
    & $runCmd
    exit $LASTEXITCODE
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
