param(
    [string]$AdminEmail = $env:ZENDOC_ADMIN_EMAIL,
    [string]$AdminPassword = $env:ZENDOC_ADMIN_PASSWORD,
    [string]$LocalModel = "llama3.2:3b",
    [int]$AsrPort = 8001
)

$ErrorActionPreference = "Stop"
$ZendocPort = 5000

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Test-AsrReady([int]$Port) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 3
        return ($health.status -eq "ready")
    } catch {
        return $false
    }
}

Require-Command "python"
Require-Command "ollama"

if (-not $AdminEmail) {
    throw "Set ZENDOC_ADMIN_EMAIL or pass -AdminEmail."
}
if (-not $AdminPassword) {
    throw "Set ZENDOC_ADMIN_PASSWORD or pass -AdminPassword."
}
if ($AdminPassword.Length -lt 12) {
    throw "Use an owner password of at least 12 characters for the local demo."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Missing .venv. Create it first with: python -m venv .venv"
}

Write-Host "Checking local Ollama model..."
$ollamaModels = & ollama list 2>$null | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "Ollama is installed but not reachable. Start the Ollama Windows app/service and run this script again."
}
if ($ollamaModels -notmatch [regex]::Escape($LocalModel)) {
    throw "Ollama model '$LocalModel' is not installed. Run: ollama pull $LocalModel"
}

Write-Host "Checking optional local ASR dependency..."
& $venvPython -c "import faster_whisper" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "faster-whisper is not installed in .venv. Run: .\.venv\Scripts\python.exe -m pip install -r requirements-edgecare-demo.txt"
}

$env:ZENDOC_ENV = "development"
if (-not $env:ZENDOC_SECRET_KEY) {
    $env:ZENDOC_SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
}
$env:ZENDOC_ADMIN_EMAIL = $AdminEmail
$env:ZENDOC_ADMIN_PASSWORD = $AdminPassword
$env:ZENDOC_EDGECARE_ENABLED = "true"

$env:ZENDOC_LOCAL_AI_ENABLED = "true"
$env:ZENDOC_LOCAL_AI_PROVIDER = "ollama"
$env:ZENDOC_LOCAL_AI_BASE_URL = "http://127.0.0.1:11434"
$env:ZENDOC_LOCAL_AI_MODEL = $LocalModel
$env:ZENDOC_LOCAL_AI_TIMEOUT = "60"

$env:ZENDOC_EDGECARE_ASR_ENABLED = "true"
$env:ZENDOC_EDGECARE_ASR_PROVIDER = "openai_compatible"
$env:ZENDOC_EDGECARE_ASR_BASE_URL = "http://127.0.0.1:$AsrPort"
$env:ZENDOC_EDGECARE_SPEECH_MODEL = "whisper_small"
$env:ZENDOC_EDGECARE_ASR_TIMEOUT = "60"
$env:EDGECARE_DEMO_ASR_PORT = "$AsrPort"

$asrReady = Test-AsrReady -Port $AsrPort
if ($asrReady) {
    Write-Host "Reusing already-running local ASR bridge on port $AsrPort."
} else {
    Write-Host "Starting local ASR bridge in a separate PowerShell window..."
    Write-Host "First startup may download the Whisper model and can take several minutes."
    $asrCommand = @"
Set-Location '$repoRoot'
`$env:EDGECARE_DEMO_ASR_PORT='$AsrPort'
& '$venvPython' -m zendoc.edgecare_demo_asr_server
"@
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $asrCommand)

    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline) {
        if (Test-AsrReady -Port $AsrPort) {
            $asrReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
}

if (-not $asrReady) {
    throw "Local ASR bridge did not become ready within 10 minutes. Check the ASR PowerShell window for details."
}

Write-Host "Local ASR bridge is ready and explicitly reports no NPU claim."
Write-Host "Starting ZENDOC at http://127.0.0.1:$ZendocPort"
Write-Host "After sign-in, open http://127.0.0.1:$ZendocPort/admin/edgecare"
Write-Host "After ZENDOC is ready, open a second terminal and run:"
Write-Host ".\.venv\Scripts\python.exe scripts\verify_edgecare_submission.py"

& $venvPython run.py
