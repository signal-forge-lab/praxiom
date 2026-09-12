[CmdletBinding()]
param(
    [int]$Port = 17679
)

$ErrorActionPreference = 'Stop'
$StateDir = Join-Path $env:LOCALAPPDATA 'praxiom-mcp'
$PidFile = Join-Path $StateDir 'mcp.pid'

try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/_shutdown" -TimeoutSec 2 | Out-Null
} catch {}

if (Test-Path $PidFile) {
    $PidValue = [int](Get-Content $PidFile -Raw)
    for ($i = 0; $i -lt 30; $i++) {
        if (-not (Get-Process -Id $PidValue -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
    $Process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $PidValue -Force
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Praxiom MCP stopped (PID $PidValue)."
} else {
    Write-Host 'Praxiom MCP is not recorded as running.'
}
