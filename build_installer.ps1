param(
    [Parameter(Position = 0)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '1.0.0'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$compiler = Get-Command 'makensis' -ErrorAction SilentlyContinue
if (-not $compiler) {
    throw 'NSIS 3 is required. Install NSIS and make sure makensis.exe is on PATH.'
}

New-Item -ItemType Directory -Force -Path (Join-Path $root 'dist') | Out-Null
Push-Location $root
try {
    & $compiler.Source "/DAPP_VERSION=$Version" 'installer/LocalAgentHub.nsi'
    if ($LASTEXITCODE -ne 0) {
        throw "NSIS exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Write-Host "Installer created: $(Join-Path $root "dist/Local-Agent-Hub-Setup-$Version.exe")"
