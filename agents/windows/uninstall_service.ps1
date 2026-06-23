#Requires -RunAsAdministrator
<#
.SYNOPSIS
    NetMon Windows Agent — Uninstaller
.EXAMPLE
    .\uninstall_service.ps1
#>

param()

$ServiceName = "NetMonAgent"
$InstallDir = "C:\Program Files\NetMon"
$ConfigDir = "C:\ProgramData\NetMon"

Write-Host "🗑️  Uninstalling NetMon Windows Agent..." -ForegroundColor Yellow

# Stop and remove service
$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host "   Stopping service..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    
    # Try Python uninstall first
    $PythonExe = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonExe) {
        & $PythonExe (Join-Path $InstallDir "netmon_service.py") stop 2>$null
        & $PythonExe (Join-Path $InstallDir "netmon_service.py") remove 2>$null
    }
    
    # Fallback: sc.exe delete
    & sc.exe delete $ServiceName 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

# Remove files
if (Test-Path $InstallDir) {
    Write-Host "   Removing $InstallDir..."
    Remove-Item -Recurse -Force $InstallDir
}

if (Test-Path $ConfigDir) {
    $keepConfig = Read-Host "   Keep configuration? (y/N)"
    if ($keepConfig -ne "y") {
        Remove-Item -Recurse -Force $ConfigDir
    }
}

Write-Host "✅ NetMon Agent uninstalled." -ForegroundColor Green
