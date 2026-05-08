param()

$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runCmd = Join-Path $rootDir "Run_Sinkhole.cmd"

if (-not (Test-Path -LiteralPath $runCmd)) {
    throw "Run_Sinkhole.cmd not found: $runCmd"
}

function New-LauncherShortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $shortcut.Save()
}

$rootShortcut = Join-Path $rootDir "Sinkhole Launcher.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Sinkhole Launcher.lnk"

if (Test-Path -LiteralPath $rootShortcut) { Remove-Item -LiteralPath $rootShortcut -Force }
if (Test-Path -LiteralPath $desktopShortcut) { Remove-Item -LiteralPath $desktopShortcut -Force }

New-LauncherShortcut -ShortcutPath $rootShortcut -TargetPath $runCmd -WorkingDirectory $rootDir
New-LauncherShortcut -ShortcutPath $desktopShortcut -TargetPath $runCmd -WorkingDirectory $rootDir

Write-Host "[INFO] Shortcuts updated."
Write-Host "[INFO] Root: $rootShortcut"
Write-Host "[INFO] Desktop: $desktopShortcut"
