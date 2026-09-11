"""Acquire an exact local public/official dataset artifact.

This command intentionally does not download URLs. Operators must obtain an
artifact through an approved/public channel, then point the command at that
file. The JSON output contains a snapshot manifest suitable for the existing
owner-only preview endpoint and never includes row values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zendoc.data_acquisition import AcquisitionError, acquire_source_file, inspect_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire one exact public dataset artifact safely.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--input", dest="input_path", required=True)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--usage-basis", required=True)
    parser.add_argument("--license-or-terms", required=True)
    parser.add_argument("--license-url")
    parser.add_argument("--dataset-version")
    parser.add_argument("--published-at")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--inspect", action="store_true", help="Include bounded schema metadata without row values.")
    args = parser.parse_args()

    try:
        result = acquire_source_file(
            args.source_id,
            args.source_url,
            args.input_path,
            storage_root=args.storage_root,
            usage_basis=args.usage_basis,
            license_or_terms=args.license_or_terms,
            license_url=args.license_url,
            dataset_version=args.dataset_version,
            published_at=args.published_at,
            retrieved_at=args.retrieved_at,
        )
        if args.inspect:
            result["schema_inspection"] = inspect_artifact(
                result["stored_path"],
                file_name=result["original_filename"],
                expected_sha256=result["file_sha256"],
            )
        # Keep local absolute paths out of machine-readable output by default.
        result.pop("stored_path", None)
    except AcquisitionError as exc:
        print(f"Dataset acquisition failed: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        # OS/parser errors may contain local paths or operator-supplied secrets.
        print("Dataset acquisition failed: the artifact or manifest could not be processed safely.", file=sys.stderr)
        return 2

    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


