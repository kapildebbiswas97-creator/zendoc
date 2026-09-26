Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found in PATH."
    }
}

Require-Command "node"
Require-Command "npm"
Require-Command "npx"

$nodeVersion = (node --version).Trim()
Write-Host "Node:" $nodeVersion
Write-Host "npm :" (npm --version)

$nodeMajor = 0
if ($nodeVersion -match '^v(?<major>\d+)') {
    $nodeMajor = [int]$Matches['major']
}
if ($nodeMajor -gt 0 -and $nodeMajor -lt 24) {
    Write-Warning "Neo base app creation may work, but the current Neo AI tooling guide recommends Node.js 24+. Upgrade before enabling its full AI/knowledge-base stack."
}
if ($env:OS -eq "Windows_NT") {
    Write-Host "Note: Neo's full ChromaDB-based AI tooling currently expects WSL/Linux on Windows."
}

$workspace = Join-Path $repoRoot "neo-workspace"
if (Test-Path $workspace) {
    throw "neo-workspace already exists. Review or remove it before bootstrapping again."
}

Write-Host "Creating isolated Neo.mjs workspace..."
npx neo-app@latest -w neo-workspace -n ZendocOps -t all -s false

if (-not (Test-Path $workspace)) {
    throw "Neo bootstrap completed without creating neo-workspace."
}

Write-Host ""
Write-Host "Neo workspace created successfully."
Write-Host "Next commands:"
Write-Host "  cd neo-workspace"
Write-Host "  npm run server-start"
Write-Host ""
Write-Host "Keep neo-workspace/.env local. Do not commit secrets."
