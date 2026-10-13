"""Emit a read-only, privacy-safe capability audit for release reviewers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from zendoc.capability_registry import get_capability_registry
from zendoc.capability_evidence_audit import build_capability_evidence_audit

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Optional output JSON path")
    args = parser.parse_args()
    manifest = json.loads(
        (ROOT / "docs" / "MUST_PRESERVE_CAPABILITY_MANIFEST.json").read_text(encoding="utf-8")
    )
    report = build_capability_evidence_audit(manifest, get_capability_registry())
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    return 0 if report["status"] == "INVENTORY_VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
