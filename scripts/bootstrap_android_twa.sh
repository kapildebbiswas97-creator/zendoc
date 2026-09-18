#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
PACKAGE_ID="${2:-}"
OUTPUT_DIR="${3:-android-twa}"

if [[ -z "$BASE_URL" || -z "$PACKAGE_ID" ]]; then
  echo "Usage: $0 https://your-domain.example com.example.zendoc [output-dir]" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"
if [[ "$BASE_URL" != https://* ]]; then
  echo "Base URL must use HTTPS." >&2
  exit 2
fi
if ! command -v npx >/dev/null 2>&1; then
  echo "Node.js/npm is required." >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  echo "Output directory already exists: $OUTPUT_DIR" >&2
  exit 2
fi

python scripts/verify_public_launch.py "$BASE_URL"
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

echo "Use Android package ID: $PACKAGE_ID"
npx --yes @bubblewrap/cli init --manifest="$BASE_URL/manifest.webmanifest"

cat <<EOF

Bubblewrap project generated.

Before Google Play release:
1. Verify targetSdk is API 36 or higher for current 2026 Play requirements.
2. Build/sign using: npx --yes @bubblewrap/cli build
3. Obtain the SHA-256 fingerprint for the final signing/App Signing key.
4. Configure on the web deployment:
   ZENDOC_ANDROID_PACKAGE_NAME=$PACKAGE_ID
   ZENDOC_ANDROID_SHA256_CERT_FINGERPRINT=<fingerprint>
5. Verify:
   $BASE_URL/.well-known/assetlinks.json
EOF
