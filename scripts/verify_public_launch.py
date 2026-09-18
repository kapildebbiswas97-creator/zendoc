#!/usr/bin/env python3
"""Verify a deployed ZENDOC public web/PWA release without mutating user data."""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


REQUIRED_PATHS = {
    "/healthz": "json",
    "/privacy": "html",
    "/terms": "html",
    "/medical-disclaimer": "html",
    "/account-deletion": "html",
    "/manifest.webmanifest": "json",
    "/sw.js": "javascript",
}


def fetch(url: str, timeout: int = 15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ZENDOC-Public-Launch-Verifier/1.0",
            "Accept": "*/*",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        body = response.read(1_000_000)
        return response.status, response.headers, body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Deployed HTTPS ZENDOC base URL, e.g. https://zendoc.example")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        print("FAIL: public launch verification requires a valid HTTPS base URL.", file=sys.stderr)
        return 2

    failures = []
    results = []

    for path, kind in REQUIRED_PATHS.items():
        url = f"{base}{path}"
        try:
            status, headers, body = fetch(url, timeout=args.timeout)
            ok = status == 200
            detail = {"path": path, "status": status}
            if kind == "json" and ok:
                try:
                    detail["json"] = json.loads(body.decode("utf-8"))
                except Exception as exc:
                    ok = False
                    detail["error"] = f"invalid JSON: {exc}"
            if path == "/manifest.webmanifest" and ok:
                manifest = detail.get("json") or {}
                if manifest.get("name") != "ZENDOC" or manifest.get("display") != "standalone":
                    ok = False
                    detail["error"] = "manifest is missing required ZENDOC standalone metadata"
                icons = manifest.get("icons") or []
                sizes = {str(item.get("sizes")) for item in icons if isinstance(item, dict)}
                if not {"192x192", "512x512"}.issubset(sizes):
                    ok = False
                    detail["error"] = "manifest is missing 192x192 or 512x512 icons"
            if path == "/sw.js" and ok:
                text = body.decode("utf-8", "replace")
                if 'url.pathname.startsWith("/api/")' not in text:
                    ok = False
                    detail["error"] = "service worker does not expose the API-cache exclusion contract"
            results.append(detail)
            if not ok:
                failures.append(detail)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            detail = {"path": path, "error": str(exc)}
            failures.append(detail)
            results.append(detail)

    assetlinks_url = f"{base}/.well-known/assetlinks.json"
    try:
        status, _headers, body = fetch(assetlinks_url, timeout=args.timeout)
        if status == 200:
            links = json.loads(body.decode("utf-8"))
            results.append({"path": "/.well-known/assetlinks.json", "status": 200, "configured": bool(links)})
        else:
            results.append({"path": "/.well-known/assetlinks.json", "status": status, "configured": False})
    except Exception:
        results.append({
            "path": "/.well-known/assetlinks.json",
            "configured": False,
            "note": "Optional for web launch; required before verified Android TWA release.",
        })

    print(json.dumps({"base_url": base, "results": results, "failures": failures}, indent=2))
    if failures:
        print("PUBLIC LAUNCH VERIFY: FAILED", file=sys.stderr)
        return 1
    print("PUBLIC LAUNCH VERIFY: CORE WEB/PWA ROUTES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
