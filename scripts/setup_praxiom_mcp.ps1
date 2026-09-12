[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BootstrapPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$McpDir = Join-Path $RepoRoot 'mcp-server'
$McpVenv = Join-Path $McpDir '.venv'
$McpPython = Join-Path $McpVenv 'Scripts\python.exe'
$IsWindowsHost = $IsWindows

if (-not (Test-Path $BootstrapPython)) {
    throw "Praxiom virtualenv is missing: $BootstrapPython"
}

if ((Test-Path $McpPython) -and $IsWindowsHost) {
    $ExistingVersion = (& $McpPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ([version]$ExistingVersion -lt [version]'3.13') {
        Remove-Item -Recurse -Force $McpVenv
    }
}

if (-not (Test-Path $McpPython)) {
    $VenvPython = $BootstrapPython
    $VenvPythonArgs = @()
    if ($IsWindowsHost) {
        $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($Launcher) {
            & $Launcher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)"
            if ($LASTEXITCODE -eq 0) {
                $VenvPython = $Launcher.Source
                $VenvPythonArgs = @('-3')
            }
        }
        if ($VenvPython -eq $BootstrapPython) {
            & $BootstrapPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)"
            if ($LASTEXITCODE -ne 0) {
                throw 'Praxiom MCP Wi-Fi on Windows requires Python 3.13+ (stdlib TLS-PSK support).'
            }
        }
    }
    & $VenvPython @VenvPythonArgs -m venv $McpVenv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Praxiom MCP virtualenv.' }
}

& $McpPython -m pip install --disable-pip-version-check -r (Join-Path $McpDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Praxiom MCP requirements.' }

& $McpPython -m pip install --disable-pip-version-check -e $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Praxiom into the MCP virtualenv.' }

Write-Host "Praxiom MCP environment ready: $McpPython"
