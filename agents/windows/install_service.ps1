#Requires -RunAsAdministrator
<#
.SYNOPSIS
    NetMon Windows Agent — PowerShell Installer Script
    
.DESCRIPTION
    Installs the NetMon Windows Agent as a Windows Service.
    Supports both Python script mode and compiled .exe mode.

.PARAMETER ServerUrl
    NetMon server URL (default: http://localhost:8000)

.PARAMETER AgentToken
    Agent token (if not provided, will auto-register via API)

.PARAMETER PollInterval
    Polling interval in seconds (default: 30)

.PARAMETER UseExe
    Use compiled .exe mode instead of Python script

.EXAMPLE
    .\install_service.ps1 -ServerUrl "http://YOUR_SERVER:8000"
    .\install_service.ps1 -ServerUrl "http://YOUR_SERVER:8000" -AgentToken "abc123..."
    .\install_service.ps1 -UseExe -ServerUrl "http://YOUR_SERVER:8000"
#>

param(
    [string]$ServerUrl = "http://localhost:8000",
    [string]$AgentToken = "",
    [int]$PollInterval = 30,
    [switch]$UseExe
)

$ErrorActionPreference = "Stop"

# ── Configuration ──────────────────────────────────────────────────
$ServiceName = "NetMonAgent"
$DisplayName = "NetMon Windows Agent"
$Description = "NetMon VM Guest Monitoring Agent"
$InstallDir = "C:\Program Files\NetMon"
$ConfigDir = "C:\ProgramData\NetMon"
$ConfigPath = Join-Path $ConfigDir "agent.conf"
$LogPath = Join-Path $ConfigDir "agent.log"
$PythonScript = Join-Path $InstallDir "netmon_agent.py"
$ExePath = Join-Path $InstallDir "netmon_agent.exe"

# ── Banner ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   NetMon Windows Agent — Installer      ║" -ForegroundColor Cyan  
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Create directories ─────────────────────────────────────────────
Write-Host "📁 Creating directories..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

# ── Copy agent files ───────────────────────────────────────────────
Write-Host "📄 Installing agent files..."
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Copy Python scripts
Copy-Item -Path (Join-Path $ScriptDir "netmon_agent.py") -Destination $InstallDir -Force
Copy-Item -Path (Join-Path $ScriptDir "netmon_service.py") -Destination $InstallDir -Force

# Copy compiled .exe if it exists
if (Test-Path (Join-Path $ScriptDir "dist\netmon_agent.exe")) {
    Copy-Item -Path (Join-Path $ScriptDir "dist\netmon_agent.exe") -Destination $InstallDir -Force
}

# ── Auto-register if no token ─────────────────────────────────────
if ([string]::IsNullOrWhiteSpace($AgentToken)) {
    Write-Host "ℹ️  No agent token provided. Auto-registering..."
    try {
        $VmName = $env:COMPUTERNAME
        $Body = @{
            name = $VmName
            location = "auto-registered"
        } | ConvertTo-Json

        $Response = Invoke-RestMethod -Uri "$ServerUrl/api/agent/register" `
            -Method POST -ContentType "application/json" -Body $Body `
            -TimeoutSec 15 -ErrorAction Stop

        $AgentToken = $Response.agent_token
        Write-Host "✅ Auto-registered VM '$VmName' — token: $($AgentToken.Substring(0,8))..." -ForegroundColor Green
    }
    catch {
        Write-Host "❌ Auto-registration failed: $_" -ForegroundColor Red
        Write-Host "   Register manually: POST $ServerUrl/api/agent/register" -ForegroundColor Yellow
        Write-Host "   Then re-run with: -AgentToken <token>" -ForegroundColor Yellow
        exit 1
    }
}

# ── Write config file ──────────────────────────────────────────────
Write-Host "⚙️  Writing configuration..."
@"
[agent]
server_url = $ServerUrl
agent_token = $AgentToken
poll_interval = $PollInterval
request_timeout = 10
"@ | Set-Content -Path $ConfigPath -Encoding UTF8

Write-Host "   Server:   $ServerUrl"
Write-Host "   Interval: ${PollInterval}s"
Write-Host "   Config:   $ConfigPath"
Write-Host ""

# ── Stop existing service if present ──────────────────────────────
$ExistingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($ExistingService) {
    Write-Host "🛑 Stopping existing service..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# ── Install service ───────────────────────────────────────────────
if ($UseExe -and (Test-Path $ExePath)) {
    Write-Host "🔧 Installing service (exe mode)..." -ForegroundColor Cyan
    
    # Use NSSM (Non-Sucking Service Manager) for .exe service wrapping
    # Check if NSSM is available
    $NssmPath = Join-Path $InstallDir "nssm.exe"
    
    if (-not (Test-Path $NssmPath)) {
        Write-Host "📦 Downloading NSSM (service wrapper)..."
        try {
            $NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
            $NssmZip = Join-Path $env:TEMP "nssm.zip"
            Invoke-WebRequest -Uri $NssmUrl -OutFile $NssmZip -UseBasicParsing
            Expand-Archive -Path $NssmZip -DestinationPath $env:TEMP -Force
            $NssmExe = Get-ChildItem -Path $env:TEMP -Recurse -Filter "nssm.exe" | 
                       Where-Object { $_.FullName -like "*win64*" } | 
                       Select-Object -First 1
            if ($NssmExe) {
                Copy-Item -Path $NssmExe.FullName -Destination $NssmPath -Force
            }
        }
        catch {
            Write-Host "⚠️  NSSM download failed. Falling back to Python service mode." -ForegroundColor Yellow
            $UseExe = $false
        }
    }
    
    if (Test-Path $NssmPath) {
        & $NssmPath install $ServiceName $ExePath
        & $NssmPath set $ServiceName AppDirectory $InstallDir
        & $NssmPath set $ServiceName AppParameters "--config `"$ConfigPath`""
        & $NssmPath set $ServiceName DisplayName $DisplayName
        & $NssmPath set $ServiceName Description $Description
        & $NssmPath set $ServiceName Start SERVICE_AUTO_START
        & $NssmPath set $ServiceName AppStdout $LogPath
        & $NssmPath set $ServiceName AppStderr $LogPath
    }
}

if (-not $UseExe) {
    Write-Host "🔧 Installing service (Python mode)..." -ForegroundColor Cyan
    
    # Find Python
    $PythonPaths = @(
        "python.exe",
        "python3.exe",
        "py.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python312\python.exe"
    )
    
    $PythonExe = $null
    foreach ($p in $PythonPaths) {
        $found = Get-Command $p -ErrorAction SilentlyContinue
        if ($found) {
            $PythonExe = $found.Source
            break
        }
    }
    
    if (-not $PythonExe) {
        Write-Host "❌ Python not found! Install Python 3.11+ and re-run." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "   Python: $PythonExe"
    
    # Install pywin32 if needed
    & $PythonExe -m pip install pywin32 psutil httpx --quiet 2>$null
    
    # Install service
    & $PythonExe (Join-Path $InstallDir "netmon_service.py") install
    
    # Configure auto-start
    & sc.exe config $ServiceName start= auto | Out-Null
}

# ── Start the service ──────────────────────────────────────────────
Write-Host "🚀 Starting service..."
Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service -and $Service.Status -eq "Running") {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║   ✅ NetMon Agent Installed & Running!  ║" -ForegroundColor Green
    Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "   Service:  Get-Service $ServiceName"
    Write-Host "   Status:   Get-Service $ServiceName | Select Status"
    Write-Host "   Stop:     Stop-Service $ServiceName"
    Write-Host "   Start:    Start-Service $ServiceName"
    Write-Host "   Remove:   sc.exe delete $ServiceName"
    Write-Host "   Logs:     $LogPath"
    Write-Host "   Config:   $ConfigPath"
    Write-Host ""
}
else {
    Write-Host ""
    Write-Host "⚠️  Service installed but status: $($Service.Status)" -ForegroundColor Yellow
    Write-Host "   Check logs: Get-Content $LogPath -Tail 50" -ForegroundColor Yellow
    Write.Host ""
}
