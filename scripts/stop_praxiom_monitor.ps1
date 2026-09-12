[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$StateDir = Join-Path $env:LOCALAPPDATA 'praxiom-monitor'
$PidFile = Join-Path $StateDir 'monitor.pid'
$UiPidFile = Join-Path $StateDir 'monitor-ui.pid'

if (Test-Path $UiPidFile) {
    $UiPidValue = [int](Get-Content $UiPidFile -Raw)
    $UiProcess = Get-Process -Id $UiPidValue -ErrorAction SilentlyContinue
    if ($UiProcess) {
        Stop-Process -Id $UiPidValue
        for ($i = 0; $i -lt 30; $i++) {
            if (-not (Get-Process -Id $UiPidValue -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 200
        }
        if (Get-Process -Id $UiPidValue -ErrorAction SilentlyContinue) {
            throw "Praxiom Monitor window PID $UiPidValue did not stop."
        }
    }
    Remove-Item $UiPidFile -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $PidFile)) {
    Write-Host 'Praxiom Monitor is not recorded as running.'
    exit 0
}

$PidValue = [int](Get-Content $PidFile -Raw)
$Process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
if ($Process) {
    Stop-Process -Id $PidValue
    for ($i = 0; $i -lt 30; $i++) {
        if (-not (Get-Process -Id $PidValue -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 200
    }
    if (Get-Process -Id $PidValue -ErrorAction SilentlyContinue) {
        throw "Praxiom Monitor PID $PidValue did not stop."
    }
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "Praxiom Monitor stopped (PID $PidValue)."
