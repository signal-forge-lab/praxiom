[CmdletBinding()]
param(
    [int]$Port = 17679,
    [switch]$MonitorFrameProjection
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$McpDir = Join-Path $RepoRoot 'mcp-server'
$McpPython = Join-Path $McpDir '.venv\Scripts\python.exe'
$Server = Join-Path $McpDir 'server.py'
$StateDir = Join-Path $env:LOCALAPPDATA 'praxiom-mcp'
$PidFile = Join-Path $StateDir 'mcp.pid'
$Stdout = Join-Path $StateDir 'mcp.stdout.log'
$Stderr = Join-Path $StateDir 'mcp.stderr.log'
$Health = "http://127.0.0.1:$Port/healthz"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path $PidFile) {
    $ExistingPid = [int](Get-Content $PidFile -Raw)
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing) {
        try {
            $Probe = Invoke-RestMethod -Uri $Health -TimeoutSec 2
            if ($Probe.ok -eq $true) {
                Write-Host "Praxiom MCP already running (PID $ExistingPid) at $Health"
                exit 0
            }
        } catch {}
        throw "Praxiom MCP PID $ExistingPid exists but health check failed. Stop it before restarting."
    }
    Remove-Item $PidFile -Force
}

if (-not (Test-Path $McpPython)) {
    & (Join-Path $PSScriptRoot 'setup_praxiom_mcp.ps1')
}

$env:PRAXIOM_MCP_HOST = '127.0.0.1'
$env:PRAXIOM_MCP_PORT = "$Port"
if ($MonitorFrameProjection) {
    $env:PRAXIOM_MONITOR_FRAME_PROJECTION = '1'
} else {
    Remove-Item Env:PRAXIOM_MONITOR_FRAME_PROJECTION -ErrorAction SilentlyContinue
}

$ServerArgument = '"' + $Server + '"'
$Process = Start-Process -FilePath $McpPython `
    -ArgumentList $ServerArgument `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $Stdout `
    -RedirectStandardError $Stderr `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $PidFile -Value $Process.Id -NoNewline

$Ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) { break }
    try {
        $Probe = Invoke-RestMethod -Uri $Health -TimeoutSec 1
        if ($Probe.ok -eq $true) { $Ready = $true; break }
    } catch {}
}

if (-not $Ready) {
    $Tail = if (Test-Path $Stderr) { (Get-Content $Stderr -Tail 30) -join [Environment]::NewLine } else { '' }
    throw "Praxiom MCP did not become healthy. PID=$($Process.Id)`n$Tail"
}

Write-Host "Praxiom MCP started: PID=$($Process.Id) MCP=http://127.0.0.1:$Port/mcp"
