[CmdletBinding()]
param(
    [int]$Port = 17680,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$StateDir = Join-Path $env:LOCALAPPDATA 'praxiom-monitor'
$PidFile = Join-Path $StateDir 'monitor.pid'
$UiPidFile = Join-Path $StateDir 'monitor-ui.pid'
$Health = "http://127.0.0.1:$Port/healthz"

$ServerPid = $null
$ServerProcess = $null
if (Test-Path $PidFile) {
    $ServerPid = [int](Get-Content $PidFile -Raw)
    $ServerProcess = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
}

$ServerReady = $false
if ($ServerProcess) {
    try {
        $Probe = Invoke-RestMethod -Uri $Health -TimeoutSec 2
        $ServerReady = $Probe.ok -eq $true
    } catch {}
}

$UiPid = $null
$UiProcess = $null
if (Test-Path $UiPidFile) {
    $UiPid = [int](Get-Content $UiPidFile -Raw)
    $UiProcess = Get-Process -Id $UiPid -ErrorAction SilentlyContinue
}
$UiReady = $null -ne $UiProcess -and $UiProcess.MainWindowHandle -ne 0

$Status = [ordered]@{
    ready = [bool]($ServerReady -and $UiReady)
    serverReady = [bool]$ServerReady
    uiReady = [bool]$UiReady
    pid = $ServerPid
    uiPid = $UiPid
    url = "http://127.0.0.1:$Port/"
}

if ($Json) {
    $Status | ConvertTo-Json -Compress
} else {
    $Status | Format-List
}
