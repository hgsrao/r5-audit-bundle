"""WP-R5-004-ISOLATED-INTEGRATION: release record validator (pure; opens no data).

A release record is a Director-issued JSON document that binds ONE release to the exact isolation profile, code-tree pins,
input pins, execution id and curated-artifact authorization sha256. It is accepted only when ALL of these hold:

* its sha256 equals an EXTERNAL pin handed in by the caller (command line / operator / ``os_isolation`` constant). A pin
  stored in the record, in the authorization or next to them is not external and is never read;
* its issuer is trusted for the record's scope by an EXTERNAL issuer table (SYNTHETIC_ONLY: caller-supplied fixture issuers;
  REAL_TRAIN_DIAGNOSTIC: ONLY the Director approval store at the fixed out-of-tree path (``real_approval``), which binds the
  exact record sha256, issuer, REAL scope, execution id and provenance acceptance receipt sha256. A caller-supplied
  ``trusted_issuers`` entry for REAL never authorizes; absent/empty store => the real release is closed);
* every binding equals the live, independently derived value (``expected``);
* the classification matches the scope: a SYNTHETIC_ONLY grant can never authorize a real-data classification.

There is no flag, no self-pinned JSON and no authorization field that grants release.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import real_approval as ra

SCHEMA = "WP004_RELEASE_RECORD_V1"
SCOPE_SYNTHETIC = "SYNTHETIC_ONLY"
SCOPE_REAL = "REAL_TRAIN_DIAGNOSTIC"
SYNTHETIC_CLASSIFICATION = "SYNTHETIC_INTEGRATION_ONLY"
REAL_CLASSIFICATION = "NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC"
SCOPE_FOR_CLASSIFICATION = {SYNTHETIC_CLASSIFICATION: SCOPE_SYNTHETIC, REAL_CLASSIFICATION: SCOPE_REAL}
REAL_TRUSTED_ISSUERS: dict = {}      # legacy constant, intentionally EMPTY and no longer consulted: REAL authority is the approval store.
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


def read_real_approval_store(forbidden_roots=(), forbidden_files=()) -> bytes:
    """HOST: the Director approval store from its fixed path (no caller-selected path). Any problem => REAL stays closed."""
    try:
        return ra.read_fixed_store(forbidden_roots, forbidden_files)
    except ra.ApprovalError as exc:
        raise ReleaseError(f"real-data release closed: {exc}") from None


def validate_release_record(record_bytes: bytes, *, external_pin, trusted_issuers, expected: dict,
                            approval_store=None) -> ReleaseGrant:
    """``external_pin``: sha256 supplied out of band. ``trusted_issuers``: {issuer: [scopes]} (only SYNTHETIC_ONLY entries
    are honoured). ``expected``: isolation_profile, classification, execution_id, authorization_sha256, code_pins, input_pins
    derived by the caller from the live/verified state (never from the record); for the REAL scope it also holds ``provenance``
    {approval_id, approval_record_sha256} taken from the validated authorization. ``approval_store``: bytes of the Director
    approval store (host: fixed path; sandbox: the witnessed read-only /in file); consulted only for the REAL scope."""
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
        prov = expected.get("provenance") or {}
        try:
            if callable(approval_store):          # host: loaded lazily, only once a REAL-scope record passed the structural checks
                approval_store = approval_store()
            ra.check_approval(approval_store, record_sha256=actual, issuer=rec["issuer"], execution_id=rec["execution_id"],
                              provenance_approval_id=prov.get("approval_id"),
                              provenance_receipt_sha256=prov.get("approval_record_sha256"),
                              authorization_sha256=rec["authorization_sha256"])
        except ra.ApprovalError as exc:
            raise ReleaseError(f"real-data release closed: {exc}") from None
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
