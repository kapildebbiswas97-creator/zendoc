param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$PackageId,
  [string]$OutputDir = "android-twa"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd('/')

if (-not $BaseUrl.StartsWith("https://")) {
  throw "BaseUrl must use HTTPS."
}
if ($PackageId -notmatch '^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$') {
  throw "PackageId must be a reverse-domain Android application ID, e.g. com.example.zendoc."
}

Write-Host "Checking live ZENDOC manifest..."
$manifest = Invoke-RestMethod -Uri "$BaseUrl/manifest.webmanifest" -Method Get
if ($manifest.name -ne "ZENDOC") {
  throw "The live manifest is not the expected ZENDOC manifest."
}

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm is required. Install Node.js, reopen PowerShell, then rerun this script."
}

if (Test-Path $OutputDir) {
  throw "Output directory '$OutputDir' already exists. Use a new directory or remove the old generated project."
}

New-Item -ItemType Directory -Path $OutputDir | Out-Null
Push-Location $OutputDir
try {
  Write-Host "Launching Bubblewrap initialization..."
  Write-Host "Use package ID: $PackageId"
  npx --yes @bubblewrap/cli init --manifest="$BaseUrl/manifest.webmanifest"

  Write-Host ""
  Write-Host "Bubblewrap project generated."
  Write-Host "IMPORTANT for 2026 Google Play submission:"
  Write-Host "  1. Verify the generated Android project targets API 36 or higher."
  Write-Host "  2. Build/sign with: npx --yes @bubblewrap/cli build"
  Write-Host "  3. Obtain the SHA-256 fingerprint for the final signing/App Signing key."
  Write-Host "  4. Set ZENDOC_ANDROID_PACKAGE_NAME=$PackageId"
  Write-Host "  5. Set ZENDOC_ANDROID_SHA256_CERT_FINGERPRINT=<fingerprint> on the web deployment."
  Write-Host "  6. Verify $BaseUrl/.well-known/assetlinks.json before release."
} finally {
  Pop-Location
}
