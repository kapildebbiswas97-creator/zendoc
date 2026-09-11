"""Streaming State/UT extraction from national LGD CSV snapshots.

This exists because national village/local-body exports can exceed the normal
in-memory pilot parser limits. It preserves the exact input columns and filters
only on the official LGD State Code column. No geography names/codes are
invented or repaired here.
"""
from __future__ import annotations

import csv
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from .lgd_files import normalize_lgd_state_code


MAX_INPUT_ROWS = 2_000_000
MAX_OUTPUT_ROWS = 500_000
MAX_INPUT_BYTES = 300 * 1024 * 1024
STATE_CODE_ALIASES = ("state code", "statecode")


def _header_key(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip().lower()
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def _detect_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def _state_field(fieldnames: list[str]) -> str:
    indexed = {_header_key(name): name for name in fieldnames if name is not None}
    for alias in STATE_CODE_ALIASES:
        if alias in indexed:
            return indexed[alias]
    raise ValueError("LGD CSV does not contain a recognized State Code column.")


def extract_state_csv(
    input_path: str | Path,
    output_path: str | Path,
    *,
    state_code: str,
    max_input_rows: int = MAX_INPUT_ROWS,
    max_output_rows: int = MAX_OUTPUT_ROWS,
    max_input_bytes: int = MAX_INPUT_BYTES,
) -> dict:
    """Filter one national LGD CSV to one State/UT without materializing all rows."""
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    wanted = normalize_lgd_state_code(state_code)
    if not wanted:
        raise ValueError("state_code is required.")
    if not source.is_file():
        raise ValueError("LGD input file was not found.")
    size = source.stat().st_size
    if size > max_input_bytes:
        raise ValueError(f"LGD input exceeds the safe {max_input_bytes} byte streaming limit.")
    if source == target:
        raise ValueError("Output path must differ from input path.")

    input_sha = hashlib.sha256()
    # Hash in bounded chunks without loading the whole national artifact.
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            input_sha.update(chunk)

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    temp = Path(temp_name)

    input_rows = 0
    matched_rows = 0
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as src:
            header_line = src.readline()
            if not header_line:
                raise ValueError("LGD CSV is empty.")
            delimiter = _detect_delimiter(header_line)
            src.seek(0)
            reader = csv.DictReader(src, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError("LGD CSV header is required.")
            state_field = _state_field(list(reader.fieldnames))

            with temp.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=reader.fieldnames, delimiter=delimiter, extrasaction="ignore")
                writer.writeheader()
                for row in reader:
                    input_rows += 1
                    if input_rows > max_input_rows:
                        raise ValueError(f"LGD input exceeds the safe {max_input_rows} row limit.")
                    if normalize_lgd_state_code(row.get(state_field)) != wanted:
                        continue
                    matched_rows += 1
                    if matched_rows > max_output_rows:
                        raise ValueError(f"State extract exceeds the safe {max_output_rows} row limit.")
                    writer.writerow({key: row.get(key, "") for key in reader.fieldnames})

        output_sha = hashlib.sha256(temp.read_bytes()).hexdigest()
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    return {
        "status": "EXTRACTED",
        "state_code": wanted,
        "input_filename": source.name,
        "input_size_bytes": size,
        "input_sha256": input_sha.hexdigest(),
        "input_rows_scanned": input_rows,
        "matched_rows": matched_rows,
        "output_filename": target.name,
        "output_sha256": output_sha,
        "truth_notice": "Rows were filtered only by official LGD State Code; no missing rows or geography identifiers were synthesized.",
    }
