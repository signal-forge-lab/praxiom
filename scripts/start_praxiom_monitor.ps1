[CmdletBinding()]
param(
    [int]$Port = 17680
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$StateDir = Join-Path $env:LOCALAPPDATA 'praxiom-monitor'
$PidFile = Join-Path $StateDir 'monitor.pid'
$Stdout = Join-Path $StateDir 'monitor.stdout.log'
$Stderr = Join-Path $StateDir 'monitor.stderr.log'
$UiPidFile = Join-Path $StateDir 'monitor-ui.pid'
$EdgeProfile = Join-Path $StateDir 'edge-profile'
$Health = "http://127.0.0.1:$Port/healthz"
$Url = "http://127.0.0.1:$Port/"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Get-EdgeExecutable {
    $Candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $Candidates += Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
    }
    if ($env:ProgramFiles) {
        $Candidates += Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
    }
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) { return $Candidate }
    }
    $Command = Get-Command msedge.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    throw 'Microsoft Edge was not found.'
}

function Start-MonitorUi {
    if (Test-Path $UiPidFile) {
        $ExistingUiPid = [int](Get-Content $UiPidFile -Raw)
        $ExistingUi = Get-Process -Id $ExistingUiPid -ErrorAction SilentlyContinue
        if ($ExistingUi -and $ExistingUi.MainWindowHandle -ne 0) { return }
        Remove-Item $UiPidFile -Force -ErrorAction SilentlyContinue
    }

    $Edge = Get-EdgeExecutable
    $UiProcess = Start-Process -FilePath $Edge `
        -ArgumentList @(
            "--app=$Url",
            "--user-data-dir=$EdgeProfile",
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-background-mode'
        ) `
        -PassThru

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        $Current = Get-Process -Id $UiProcess.Id -ErrorAction SilentlyContinue
        if ($Current -and $Current.MainWindowHandle -ne 0) {
            Set-Content -Path $UiPidFile -Value $Current.Id -NoNewline
            return
        }
        if (-not $Current) { break }
    }
    throw "Praxiom Monitor window did not become visible. Edge PID=$($UiProcess.Id)"
}

if (Test-Path $PidFile) {
    $ExistingPid = [int](Get-Content $PidFile -Raw)
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing) {
        try {
            $Probe = Invoke-RestMethod -Uri $Health -TimeoutSec 2
            if ($Probe.ok -eq $true) {
                Start-MonitorUi
                Write-Host "Praxiom Monitor already running (PID $ExistingPid) at $Health"
                exit 0
            }
        } catch {}
        throw "Praxiom Monitor PID $ExistingPid exists but health check failed. Stop it before restarting."
    }
    Remove-Item $PidFile -Force
}

if (-not (Test-Path $Python)) {
    throw "Praxiom venv Python not found: $Python"
}

$Process = Start-Process -FilePath $Python `
    -ArgumentList @('-m', 'praxiom.monitor.server', '--host', '127.0.0.1', '--port', "$Port") `
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
    throw "Praxiom Monitor did not become healthy. PID=$($Process.Id)`n$Tail"
}

Start-MonitorUi
Write-Host "Praxiom Monitor started: PID=$($Process.Id) URL=$Url"
