"""WP-R5-004-ISOLATED-INTEGRATION: release record validator (pure; opens no data).

A release record is a Director-issued JSON document that binds ONE release to the exact isolation profile, code-tree pins,
input pins, execution id and curated-artifact authorization sha256. It is accepted only when ALL of these hold:

* its sha256 equals an EXTERNAL pin handed in by the caller (command line / operator / ``os_isolation`` constant). A pin
  stored in the record, in the authorization or next to them is not external and is never read;
* its issuer is trusted for the record's scope by an EXTERNAL issuer table (SYNTHETIC_ONLY: caller-supplied fixture issuers;
  REAL_TRAIN_DIAGNOSTIC: ``REAL_TRUSTED_ISSUERS`` below, which is EMPTY, and ``os_isolation.REAL_RUN_RELEASE_ACCEPTANCE_SHA256``,
  which is ``None``: the real release is closed and no code path in this module opens it);
* every binding equals the live, independently derived value (``expected``);
* the classification matches the scope: a SYNTHETIC_ONLY grant can never authorize a real-data classification.

There is no flag, no self-pinned JSON and no authorization field that grants release.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

SCHEMA = "WP004_RELEASE_RECORD_V1"
SCOPE_SYNTHETIC = "SYNTHETIC_ONLY"
SCOPE_REAL = "REAL_TRAIN_DIAGNOSTIC"
SYNTHETIC_CLASSIFICATION = "SYNTHETIC_INTEGRATION_ONLY"
REAL_CLASSIFICATION = "NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC"
SCOPE_FOR_CLASSIFICATION = {SYNTHETIC_CLASSIFICATION: SCOPE_SYNTHETIC, REAL_CLASSIFICATION: SCOPE_REAL}
REAL_TRUSTED_ISSUERS: dict = {}      # issuer -> scopes. EMPTY: no Director-approved real issuer exists. Not configurable at runtime.
_KEYS = {"schema", "record_id", "issuer", "release_scope", "isolation_profile", "classification", "execution_id",
         "authorization_sha256", "code_pins", "input_pins"}
_HEX = re.compile(r"[0-9a-f]{64}")


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class ReleaseGrant:
    scope: str
    record_id: str
    issuer: str
    record_sha256: str
    classification: str
    execution_id: str
    authorization_sha256: str

    @property
    def authorizes_real_classification(self) -> bool:
        return self.scope == SCOPE_REAL


def _is_sha(value) -> bool:
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def _real_pin():
    import os_isolation as osi
    return osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256


def validate_release_record(record_bytes: bytes, *, external_pin, trusted_issuers, expected: dict) -> ReleaseGrant:
    """``external_pin``: sha256 supplied out of band. ``trusted_issuers``: {issuer: [scopes]} (only SYNTHETIC_ONLY entries
    are honoured). ``expected``: isolation_profile, classification, execution_id, authorization_sha256, code_pins, input_pins
    derived by the caller from the live/verified state (never from the record)."""
    if not _is_sha(external_pin):
        raise ReleaseError("release record: external pin missing or malformed (no self-pinned release)")
    actual = hashlib.sha256(record_bytes).hexdigest()
    if actual != external_pin:
        raise ReleaseError("release record sha256 differs from the external pin")
    try:
        rec = json.loads(record_bytes)
    except ValueError as exc:
        raise ReleaseError(f"release record is not valid JSON: {exc}") from None
    if not isinstance(rec, dict) or set(rec) != _KEYS:
        raise ReleaseError(f"release record keys must be exactly {sorted(_KEYS)}")
    if rec["schema"] != SCHEMA:
        raise ReleaseError("release record schema mismatch")
    for key in ("record_id", "issuer", "execution_id", "isolation_profile"):
        if not isinstance(rec[key], str) or not rec[key].strip():
            raise ReleaseError(f"release record {key} missing")
    scope = rec["release_scope"]
    if scope not in (SCOPE_SYNTHETIC, SCOPE_REAL):
        raise ReleaseError(f"unknown release scope {scope!r}")
    if SCOPE_FOR_CLASSIFICATION.get(rec["classification"]) != scope:
        raise ReleaseError(f"release scope {scope} does not match classification {rec['classification']!r}")
    if scope == SCOPE_REAL:
        if not REAL_TRUSTED_ISSUERS or rec["issuer"] not in REAL_TRUSTED_ISSUERS or _real_pin() != actual:
            raise ReleaseError("real-data release closed: no Director-approved real issuer / "
                               "REAL_RUN_RELEASE_ACCEPTANCE_SHA256 pin exists for this record")
    else:
        scopes = (trusted_issuers or {}).get(rec["issuer"])
        if not scopes or scope not in scopes:
            raise ReleaseError(f"issuer {rec['issuer']!r} is not externally trusted for scope {scope}")
    if not _is_sha(rec["authorization_sha256"]):
        raise ReleaseError("release record authorization_sha256 malformed")
    for key in ("isolation_profile", "classification", "execution_id", "authorization_sha256"):
        if rec[key] != expected[key]:
            raise ReleaseError(f"release record {key} differs from the live value")
    for key in ("code_pins", "input_pins"):
        pins = rec[key]
        if not isinstance(pins, dict) or not pins or not all(_is_sha(v) for v in pins.values()):
            raise ReleaseError(f"release record {key} malformed")
        if pins != dict(expected[key]):
            raise ReleaseError(f"release record {key} differ from the live pins (exact set and values required)")
    return ReleaseGrant(scope=scope, record_id=rec["record_id"], issuer=rec["issuer"], record_sha256=actual,
                        classification=rec["classification"], execution_id=rec["execution_id"],
                        authorization_sha256=rec["authorization_sha256"])
