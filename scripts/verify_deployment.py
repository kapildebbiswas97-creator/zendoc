"""Verify a deployed ZENDOC instance using public liveness/readiness only."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def fail(message: str) -> None:
    print(f"Deployment verification FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def get_json(url: str, timeout: float) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ZENDOC-Deployment-Verifier/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
            return int(response.status), json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read(1024 * 1024)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}
        return int(error.code), payload
    except Exception as error:
        fail(f"Could not reach {url}: {type(error).__name__}")


def safe_payload_summary(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    allowed = ("status", "service", "check", "database", "database_engine", "persistence_verified")
    summary = {key: payload.get(key) for key in allowed if key in payload}
    deployment = payload.get("deployment")
    if isinstance(deployment, dict):
        summary["deployment"] = {
            key: deployment.get(key)
            for key in ("platform", "service_name", "git_commit", "git_commit_short")
            if key in deployment
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--expected-commit")
    parser.add_argument("--require-platform")
    parser.add_argument("--require-engine")
    parser.add_argument("--require-persistence-verified", action="store_true")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        fail("base_url must be an absolute http(s) URL.")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        fail("Remote deployment verification requires HTTPS.")

    attempts = max(1, int(args.attempts or 1))
    interval = max(0.0, float(args.interval or 0.0))
    last_error = None
    health = {}
    ready = {}
    for attempt in range(1, attempts + 1):
        try:
            health_status, health = get_json(f"{base}/api/v1/health", args.timeout)
            if health_status != 200 or health.get("status") != "ok" or health.get("check") != "liveness":
                raise RuntimeError(
                    f"Liveness check failed with HTTP {health_status}: {safe_payload_summary(health)}"
                )

            ready_status, ready = get_json(f"{base}/api/v1/ready", args.timeout)
            if ready_status != 200 or ready.get("status") != "ready":
                raise RuntimeError(
                    f"Readiness check failed with HTTP {ready_status}: {safe_payload_summary(ready)}"
                )

            deployment = ready.get("deployment") or {}
            if args.expected_commit:
                deployed_commit = str(deployment.get("git_commit") or "").strip()
                expected_commit = str(args.expected_commit).strip()
                if not deployed_commit or deployed_commit.lower() != expected_commit.lower():
                    raise RuntimeError(
                        f"Deployed commit not ready yet: expected {expected_commit}, got {deployed_commit or 'missing'}."
                    )
            last_error = None
            break
        except SystemExit:
            raise
        except Exception as error:
            last_error = str(error)
            if attempt >= attempts:
                fail(last_error)
            print(f"Deployment verification attempt {attempt}/{attempts} not ready: {last_error}")
            time.sleep(interval)

    if last_error:
        fail(last_error)

    if ready.get("database") != "reachable":
        fail("Readiness did not confirm database reachability.")
    migrations = ready.get("migrations") or {}
    schema = ready.get("schema") or {}
    if not migrations.get("ready") or migrations.get("missing_migrations"):
        fail(f"Migration readiness failed: {migrations}")
    if not schema.get("ready") or schema.get("missing_tables"):
        fail(f"Schema readiness failed: {schema}")

    deployment = ready.get("deployment") or {}
    if args.require_platform and deployment.get("platform") != args.require_platform:
        fail(
            f"Expected deployment platform {args.require_platform!r}, "
            f"got {deployment.get('platform')!r}."
        )

    if args.expected_commit:
        deployed_commit = str(deployment.get("git_commit") or "").strip()
        expected_commit = str(args.expected_commit).strip()
        if not deployed_commit:
            fail("Readiness did not expose the deployed Git commit.")
        if deployed_commit.lower() != expected_commit.lower():
            fail(
                f"Deployed commit mismatch: expected {expected_commit}, "
                f"got {deployed_commit}."
            )

    if args.require_engine and ready.get("database_engine") != args.require_engine:
        fail(
            f"Expected database engine {args.require_engine!r}, "
            f"got {ready.get('database_engine')!r}."
        )

    if args.require_persistence_verified and ready.get("persistence_verified") is not True:
        fail("Production persistence verification is not confirmed.")

    print(
        "Deployment verification PASSED "
        f"(platform={deployment.get('platform')}, commit={deployment.get('git_commit_short')}, "
        f"engine={ready.get('database_engine')}, db_latency_ms={ready.get('database_latency_ms')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
