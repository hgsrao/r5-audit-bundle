#!/usr/bin/env python3
"""WP-R5-001C: acquire the NSE instrument master through the official Kite Connect OAuth flow.

Interactive and operator-driven:
  1. prints the official Kite login URL; the OPERATOR logs in on Zerodha's page (password / TOTP are typed there, never here);
  2. the operator pastes the redirected URL (or the bare request_token);
  3. the script exchanges it (generate_session), downloads GET /instruments/NSE UNCHANGED, hashes and records provenance,
     invalidates the session, and (optionally) submits and dispatches the qualification package through the Engineering Dispatcher.

Secrets: the API key / secret come from KITE_API_KEY / KITE_API_SECRET or hidden prompts; they and the access token live in memory only.
Nothing secret is written to disk, printed or logged (an automatic post-run scan enforces this).  Read-only API use: login, one
instruments download, token invalidation.  No orders, no positions, no account data.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "kite_connect.json"
SENSITIVE_HEADERS = {"set-cookie", "authorization", "cookie"}
QUALIFICATION_PACKAGE = ROOT / "work" / "packages" / "WP-R5-001C-QUAL.json"


class AcquisitionError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_settings(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    settings = json.loads(Path(path).read_text())
    for key in ("exchange", "login_base", "instruments_endpoint", "kite_version_header", "api_key_env", "api_secret_env",
                "output_dir", "raw_file_name", "timeout_seconds"):
        if key not in settings:
            raise AcquisitionError(f"configuration lacks {key}")
    return settings


def _clean_credential(value: str) -> str:
    """Trim whitespace and copy/paste wrappers (markdown backticks, quotes) only; the value itself is never altered."""
    return value.strip().strip("`'\"").strip()


def read_credentials(settings: dict[str, Any], environ: dict[str, str] | None = None,
                     prompt: Callable[[str], str] = getpass.getpass) -> tuple[str, str]:
    """API key and secret: environment first, otherwise a HIDDEN prompt.  Never echoed, stored or logged."""
    env = os.environ if environ is None else environ
    api_key = env.get(settings["api_key_env"]) or prompt("Kite Connect API key (hidden): ")
    api_secret = env.get(settings["api_secret_env"]) or prompt("Kite Connect API secret (hidden): ")
    api_key, api_secret = (_clean_credential(v) for v in (api_key, api_secret))
    if not api_key or not api_secret:
        raise AcquisitionError("an API key and an API secret are required")
    for name, value in (("API key", api_key), ("API secret", api_secret)):
        if not value.isalnum():
            raise AcquisitionError(f"the {name} contains characters other than letters and digits (stray quote, backtick or space from copy/paste?); nothing was sent to Kite")
    return api_key, api_secret


def login_url(settings: dict[str, Any], api_key: str) -> str:
    return f"{settings['login_base']}?v=3&api_key={api_key}"


def parse_request_token(text: str) -> str:
    """Accept the full redirected URL or the bare request_token; refuse failed logins and anything ambiguous."""
    text = (text or "").strip()
    if not text:
        raise AcquisitionError("no request token supplied")
    if "://" in text or "?" in text:
        query = parse_qs(urlparse(text if "://" in text else "https://x/?" + text.split("?", 1)[-1]).query)
        if query.get("status", ["success"])[0] != "success":
            raise AcquisitionError(f"login did not succeed (status={query['status'][0]})")
        token = (query.get("request_token") or [""])[0]
    else:
        token = text
    if not token.isalnum():
        raise AcquisitionError("the request token must be alphanumeric")
    return token


def fetch_instruments(settings: dict[str, Any], api_key: str, access_token: str,
                      opener: Callable[..., Any] = urlopen) -> tuple[int, dict[str, str], bytes, str]:
    """Official endpoint, raw bytes returned unchanged.  The token is sent only in the Authorization header."""
    url = settings["instruments_endpoint"].format(exchange=settings["exchange"])
    request = Request(url, headers={"X-Kite-Version": str(settings["kite_version_header"]),
                                    "Authorization": f"token {api_key}:{access_token}"})
    with opener(request, timeout=settings["timeout_seconds"]) as response:
        return response.status, {k: v for k, v in response.headers.items()}, response.read(), url


def validate_download(status: int, headers: dict[str, str], body: bytes) -> int:
    if status != 200:
        raise AcquisitionError(f"unexpected HTTP status {status}")
    if not body.startswith(b"instrument_token,exchange_token,tradingsymbol"):
        raise AcquisitionError("the response is not an instruments CSV (header mismatch; an error body is never saved as data)")
    rows = body.count(b"\n") - 1
    if rows < 100:
        raise AcquisitionError(f"implausibly small instrument list ({rows} rows)")
    return rows


def write_artifacts(outdir: Path, raw_name: str, body: bytes, headers: dict[str, str], record: dict[str, Any]) -> dict[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    raw = outdir / raw_name
    if raw.exists():
        raise AcquisitionError(f"{raw} already exists; raw acquisitions are never overwritten")
    raw.write_bytes(body)                                                   # unchanged bytes
    safe_headers = {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_HEADERS}
    (outdir / f"{raw_name}.headers.json").write_text(json.dumps(safe_headers, indent=2, sort_keys=True))
    record = dict(record, raw_file=raw_name, size_bytes=len(body), sha256=sha256_bytes(body))
    (outdir / "ACQUISITION_RECORD.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    sums = "".join(f"{sha256_bytes((outdir / n).read_bytes())}  {n}\n"
                   for n in (raw_name, f"{raw_name}.headers.json", "ACQUISITION_RECORD.json"))
    (outdir / "SHA256SUMS.txt").write_text(sums)
    return {"raw": str(raw), "sha256": record["sha256"]}


def assert_no_secrets(outdir: Path, secrets: list[str]) -> None:
    """Post-run guard: none of the secrets may appear in any file written to the output directory."""
    for path in sorted(outdir.rglob("*")):
        if path.is_file():
            content = path.read_bytes()
            for secret in secrets:
                if secret and secret.encode() in content:
                    path.unlink()
                    raise AcquisitionError(f"a secret was found in {path.name}; the file was deleted")


def acquire(settings: dict[str, Any], *, api_key: str, api_secret: str, token_text: str, kite_factory: Callable[..., Any],
            opener: Callable[..., Any] = urlopen, now: Callable[[], str] = utc_now) -> dict[str, Any]:
    started = now()
    request_token = parse_request_token(token_text)
    kite = kite_factory(api_key=api_key)
    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]
    secrets = [api_secret, access_token, request_token]
    try:
        status, headers, body, url = fetch_instruments(settings, api_key, access_token, opener)
        rows = validate_download(status, headers, body)
    finally:
        invalidated, invalidate_error = False, None
        if settings.get("invalidate_session_after_download"):
            try:
                kite.invalidate_access_token(access_token)
                invalidated = True
            except Exception as exc:                                        # noqa: BLE001 - recorded, never fatal
                invalidate_error = type(exc).__name__
    try:
        import kiteconnect
        library = getattr(kiteconnect, "__version__", None)
        library = getattr(library, "__version__", library)
    except Exception:                                                       # noqa: BLE001
        library = None
    record = {"acquired_by": "operator-completed official Kite Connect OAuth login", "download_started_utc": started,
              "download_finished_utc": now(), "endpoint": url, "http_status": status, "instrument_rows": rows,
              "api_key_fingerprint_sha256_12": sha256_bytes(api_key.encode())[:12], "kiteconnect_library": str(library),
              "python": platform.python_version(), "auth_flow": "login URL -> request_token -> generate_session -> GET /instruments/NSE",
              "access_token_stored": False, "api_secret_stored": False, "session_invalidated": invalidated,
              "invalidate_error": invalidate_error, "response_content_type": headers.get("Content-Type", headers.get("content-type"))}
    outdir = Path(settings["output_dir"])
    written = write_artifacts(outdir, settings["raw_file_name"], body, headers, record)
    assert_no_secrets(outdir, secrets)
    return {**written, "rows": rows, "outdir": str(outdir), "session_invalidated": invalidated}


def dispatch_qualification(python: str, platform_root: Path) -> int:
    """Submit and run the qualification package THROUGH the dispatcher (never a direct worker call)."""
    base = [python, "-m", "engineering_dispatcher.dispatcher", "--config", str(platform_root / "config" / "dispatcher.json")]
    if subprocess.run(base + ["--submit", str(QUALIFICATION_PACKAGE)], cwd=platform_root).returncode != 0:
        return 2
    return subprocess.run(base + ["--once"], cwd=platform_root).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--then-dispatch", action="store_true", help="after a successful acquisition, run the qualification package via the dispatcher")
    args = parser.parse_args(argv)
    settings = load_settings(Path(args.config))
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("The kiteconnect package is required (use the zerodha-phase1-r5 virtual environment).", file=sys.stderr)
        return 2
    try:
        api_key, api_secret = read_credentials(settings)
        print("\n=== STEP 1: log in (you, not this script) ===")
        print("Open this official Zerodha login URL in your browser and log in with your own credentials and TOTP:\n")
        print("   " + login_url(settings, api_key) + "\n")
        print("After login your browser is redirected to your registered redirect URL (the page may not load; that is fine).")
        print("Copy the FULL address from the browser bar (it contains request_token=...&status=success).\n")
        token_text = input("Paste the redirected URL (or just the request_token) and press Enter: ")
        print("\n=== STEP 2: acquisition (automatic) ===")
        result = acquire(settings, api_key=api_key, api_secret=api_secret, token_text=token_text, kite_factory=KiteConnect)
    except AcquisitionError as exc:
        print(f"ACQUISITION FAILED (nothing was saved as data): {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                                                # noqa: BLE001
        print(f"ACQUISITION FAILED: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1
    print(f"Saved {result['rows']} instruments to {result['raw']}\nSHA-256: {result['sha256']}\nSession invalidated: {result['session_invalidated']}")
    if args.then_dispatch:
        print("\n=== STEP 3: qualification via the Engineering Dispatcher ===")
        return dispatch_qualification(sys.executable, ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
