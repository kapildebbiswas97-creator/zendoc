#!/usr/bin/env python3
"""Static verifier for a Bubblewrap-generated ZENDOC Android project."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TARGET_PATTERNS = (
    re.compile(r"targetSdkVersion\s*[=: ]\s*(\d+)"),
    re.compile(r"targetSdk\s*[=: ]\s*(\d+)"),
)
APP_ID_PATTERNS = (
    re.compile(r"applicationId\s*[= ]\s*[\"']([^\"']+)[\"']"),
    re.compile(r"namespace\s*[= ]\s*[\"']([^\"']+)[\"']"),
)


def scan_text(root: Path):
    candidates = [
        root / "app" / "build.gradle",
        root / "app" / "build.gradle.kts",
        root / "build.gradle",
        root / "build.gradle.kts",
        root / "twa-manifest.json",
    ]
    texts = []
    for path in candidates:
        if path.exists():
            texts.append((path, path.read_text(encoding="utf-8", errors="replace")))
    return texts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", nargs="?", default="android-twa")
    parser.add_argument("--expected-package")
    parser.add_argument("--minimum-target-sdk", type=int, default=36)
    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    if not root.exists():
        print(f"FAIL: Android project does not exist: {root}", file=sys.stderr)
        return 2

    texts = scan_text(root)
    if not texts:
        print("FAIL: no Gradle/TWA manifest files found.", file=sys.stderr)
        return 2

    target_values = []
    package_values = []
    for path, text in texts:
        for pattern in TARGET_PATTERNS:
            target_values.extend(int(value) for value in pattern.findall(text))
        for pattern in APP_ID_PATTERNS:
            package_values.extend(pattern.findall(text))
        if path.name == "twa-manifest.json":
            try:
                manifest = json.loads(text)
                package = manifest.get("packageId") or manifest.get("applicationId")
                if package:
                    package_values.append(str(package))
            except Exception:
                pass

    if not target_values:
        print("FAIL: target SDK could not be resolved from generated Android project.", file=sys.stderr)
        return 1
    target = max(target_values)
    if target < args.minimum_target_sdk:
        print(
            f"FAIL: target SDK {target} is below required minimum {args.minimum_target_sdk}.",
            file=sys.stderr,
        )
        return 1

    if args.expected_package and args.expected_package not in set(package_values):
        print(
            f"FAIL: expected package {args.expected_package!r} not found; discovered {sorted(set(package_values))}.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps({
        "status": "pass",
        "project": str(root),
        "target_sdk": target,
        "minimum_target_sdk": args.minimum_target_sdk,
        "packages": sorted(set(package_values)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
