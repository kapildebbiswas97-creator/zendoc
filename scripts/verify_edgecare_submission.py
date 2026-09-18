"""Read-only preflight for the ZENDOC EdgeCare AI competition demo.

Run this after the local LLM, local ASR bridge and ZENDOC app are started.
It verifies repository/runtime prerequisites without creating benchmark evidence
or making Snapdragon/NPU claims.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EXPECTED_BRANCH = "competition/edgecare-ai-2026"
REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "requirements.txt",
    "requirements-edgecare-demo.txt",
    "docs/EDGECARE_AI_2026.md",
    "docs/EDGECARE_LOCAL_DEMO_SETUP.md",
    "docs/EDGECARE_SUBMISSION_READINESS.md",
    "docs/QUALCOMM_AI_HUB_RUNTIME_SETUP.md",
    "docs/QUALCOMM_SNAPDRAGON_AI_LAB_2026_SUBMISSION.md",
    "scripts/start_edgecare_local_demo.ps1",
    "zendoc/edgecare_demo_asr_server.py",
    "zendoc/edgecare_routes.py",
)


def _run(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def _json_get(url: str, timeout: int = 5) -> tuple[bool, dict[str, Any] | None, str]:
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback/configured local preflight only
            payload = json.loads(response.read().decode("utf-8"))
        return isinstance(payload, dict), payload if isinstance(payload, dict) else None, ""
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return False, None, str(exc)


def _model_ids(payload: dict[str, Any] | None) -> set[str]:
    if not payload:
        return set()
    items = payload.get("data") or payload.get("models") or []
    found: set[str] = set()
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                for key in ("id", "name", "model"):
                    value = item.get(key)
                    if value:
                        found.add(str(value))
    return found


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    failures: list[str] = []
    warnings: list[str] = []

    def passed(label: str, detail: str = "") -> None:
        print(f"[PASS] {label}" + (f" — {detail}" if detail else ""))

    def failed(label: str, detail: str = "") -> None:
        failures.append(label)
        print(f"[FAIL] {label}" + (f" — {detail}" if detail else ""))

    def warn(label: str, detail: str = "") -> None:
        warnings.append(label)
        print(f"[INFO] {label}" + (f" — {detail}" if detail else ""))

    print("ZENDOC EdgeCare AI — competition submission preflight")
    print("This checks software/runtime readiness only; it does not prove Snapdragon/NPU execution.\n")

    code, branch = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if code == 0 and branch == EXPECTED_BRANCH:
        passed("Competition branch", branch)
    else:
        failed("Competition branch", branch or "git branch unavailable")

    code, commit = _run("git", "rev-parse", "HEAD")
    if code == 0 and len(commit) >= 7:
        passed("Git commit recorded", commit)
    else:
        failed("Git commit recorded", commit or "unavailable")

    missing = [name for name in REQUIRED_FILES if not (repo_root / name).is_file()]
    if not missing:
        passed("Required submission files present", f"{len(REQUIRED_FILES)} files")
    else:
        failed("Required submission files present", ", ".join(missing))

    if importlib.util.find_spec("faster_whisper") is not None:
        passed("Faster-Whisper dependency installed")
    else:
        failed(
            "Faster-Whisper dependency installed",
            "install requirements-edgecare-demo.txt in the active environment",
        )

    local_provider = (os.environ.get("ZENDOC_LOCAL_AI_PROVIDER") or "ollama").strip().lower()
    local_base = (os.environ.get("ZENDOC_LOCAL_AI_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    local_model = (os.environ.get("ZENDOC_LOCAL_AI_MODEL") or "llama3.2:3b").strip()

    if local_provider == "ollama":
        ok, payload, error = _json_get(f"{local_base}/api/tags")
        if ok:
            ids = _model_ids(payload)
            if local_model in ids or any(item.startswith(local_model + ":") for item in ids):
                passed("Local LLM runtime ready", f"ollama / {local_model}")
            else:
                failed("Local LLM model available", f"{local_model} not found; available={sorted(ids)}")
        else:
            failed("Local LLM runtime ready", error)
    elif local_provider in {"openai_compatible", "openai-compatible"}:
        ok, payload, error = _json_get(f"{local_base}/v1/models")
        if ok:
            ids = _model_ids(payload)
            if not local_model or local_model in ids:
                passed("Local LLM runtime ready", f"openai-compatible / {local_model or 'configured model'}")
            else:
                failed("Local LLM model available", f"{local_model} not found; available={sorted(ids)}")
        else:
            failed("Local LLM runtime ready", error)
    else:
        failed("Supported local LLM provider", local_provider)

    asr_base = (os.environ.get("ZENDOC_EDGECARE_ASR_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")
    speech_model = (os.environ.get("ZENDOC_EDGECARE_SPEECH_MODEL") or "whisper_small").strip()
    ok, health, error = _json_get(f"{asr_base}/healthz")
    if ok and str((health or {}).get("status") or "").lower() == "ready":
        backend = str((health or {}).get("backend") or "local-asr")
        passed("Local ASR runtime ready", backend)
        if (health or {}).get("npu_confirmed") is True:
            warn("ASR reports NPU confirmation", "retain the real source evidence before making this claim")
        else:
            warn("ASR NPU claim", "not confirmed — correct for the Faster-Whisper development bridge")
    else:
        failed("Local ASR runtime ready", error or str(health))

    ok, models, error = _json_get(f"{asr_base}/v1/models")
    if ok:
        ids = _model_ids(models)
        if speech_model in ids:
            passed("Configured ASR model available", speech_model)
        else:
            failed("Configured ASR model available", f"{speech_model} not found; available={sorted(ids)}")
    else:
        failed("Configured ASR model available", error)

    app_base = (os.environ.get("ZENDOC_PREFLIGHT_APP_BASE_URL") or "http://127.0.0.1:5000").rstrip("/")
    ok, app_health, error = _json_get(f"{app_base}/healthz")
    if ok and str((app_health or {}).get("status") or "").lower() == "ready":
        passed("ZENDOC application health", app_base)
    else:
        failed("ZENDOC application health", error or str(app_health))

    benchmark_path = Path(
        os.environ.get("ZENDOC_EDGECARE_BENCHMARK_FILE") or "instance/edgecare_benchmark.json"
    )
    if benchmark_path.exists():
        try:
            evidence = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failed("Benchmark evidence file valid JSON", str(exc))
        else:
            required = {
                "schema_version",
                "source",
                "measured_at",
                "device",
                "chipset",
                "runtime",
                "execution_provider",
                "model",
                "runs",
                "success_rate",
                "median_latency_ms",
                "p95_latency_ms",
                "npu_confirmed",
                "evidence_reference",
            }
            missing_fields = sorted(required.difference(evidence if isinstance(evidence, dict) else {}))
            if missing_fields:
                failed("Benchmark evidence schema", "missing: " + ", ".join(missing_fields))
            else:
                passed("Benchmark evidence schema", str(benchmark_path))
                if evidence.get("npu_confirmed") is True:
                    warn("Recorded NPU evidence", "keep the raw Qualcomm/device report with the submission")
                else:
                    warn("Recorded benchmark", "NPU is explicitly unconfirmed")
    else:
        warn(
            "Snapdragon/NPU benchmark evidence",
            "not recorded; do not claim measured NPU execution or latency",
        )

    print("\nManual browser checks still required on the actual demo machine:")
    print("  1. Sign in as owner and open /admin/edgecare.")
    print("  2. Confirm Local AI = ready and Local ASR = ready.")
    print("  3. Run the fixed harmless local-AI smoke test.")
    print("  4. Test microphone -> editable transcript -> manual Send.")
    print("  5. Run the exact demo pages once and confirm no 404/500.")
    print("These cannot be truthfully certified by repository CI because they depend on the real browser/microphone/runtime.\n")

    if failures:
        print(f"PRE-FLIGHT RESULT: NOT READY ({len(failures)} blocking check(s) failed)")
        return 1

    print("PRE-FLIGHT RESULT: SOFTWARE RUNTIME READY")
    if warnings:
        print(f"Informational truth/evidence notes: {len(warnings)}")
    print("This result is not Snapdragon/NPU benchmark proof.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
