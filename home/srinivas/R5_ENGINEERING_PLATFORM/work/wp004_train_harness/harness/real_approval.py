"""WP-R5-004-RELEASE-AUTHORITY: the Director-controlled REAL approval store (pure; opens no artifact data).

REAL release authority is DATA that lives OUTSIDE the pinned code tree, at ONE fixed path (``FIXED_STORE_PATH``). Nothing selects
that path: no config key, JSON field, environment variable or command-line option (tests monkeypatch the module constant; the
runtime has no override). The store is absent/empty until the Director creates it, and missing/empty/malformed always denies REAL.

Store schema (``WP004_REAL_APPROVAL_STORE_V1``), exactly these keys, nothing else::

    {"schema": "WP004_REAL_APPROVAL_STORE_V1",
     "approvals": [{"approval_id": str,                      # Director's id for this approval
                    "record_sha256": hex64,                  # exact sha256 of the release-record bytes
                    "issuer": str,                           # must equal record.issuer
                    "release_scope": "REAL_TRAIN_DIAGNOSTIC",# the only scope this store can grant
                    "execution_id": str,                     # must equal the live execution id
                    "provenance_approval_id": str,           # must equal authorization.provenance.approval_id
                    "provenance_receipt_sha256": hex64}]}    # must equal authorization.provenance.approval_record_sha256

``provenance_receipt_sha256`` is the sha256 of the externally issued provenance acceptance receipt. It is an input the Director
types in after that receipt exists; it is never derived here, and a value equal to the record or authorization hash is refused.
The store is not itself pinned in the release record (it binds the record's hash, so pinning it would be circular); its integrity
comes from the fixed location, the Director-only write permission check below, and the host-witnessed read-only /in mount.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat

FIXED_STORE_PATH = "/home/srinivas/R5_ENGINEERING_PLATFORM/authority/wp004_real_approvals.json"
STORE_SCHEMA = "WP004_REAL_APPROVAL_STORE_V1"
REAL_SCOPE = "REAL_TRAIN_DIAGNOSTIC"
APPROVAL_ALIAS = "real_approvals.json"                      # individual read-only file under /in (REAL runs only)
STORE_LABEL = "DIRECTOR-FIXED-APPROVAL-STORE"               # InputArtifact.approval_id recorded in the host OS witness
MAX_STORE_BYTES = 1 << 20
_STORE_KEYS = {"schema", "approvals"}
_ENTRY_KEYS = {"approval_id", "record_sha256", "issuer", "release_scope", "execution_id", "provenance_approval_id",
               "provenance_receipt_sha256"}
_HEX = re.compile(r"[0-9a-f]{64}")


class ApprovalError(Exception):
    pass


def _is_sha(value) -> bool:
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def read_fixed_store(forbidden_roots=(), forbidden_files=()) -> bytes:
    """HOST: bytes of the store at the fixed path. Refuses a missing/empty/non-plain/oversized/group-or-world-writable file and
    any store that lives inside caller-reachable trees (the pinned code roots, the output dir) or IS a caller-supplied file."""
    path = FIXED_STORE_PATH
    try:
        st = os.lstat(path)
    except OSError:
        raise ApprovalError("approval store missing") from None
    if not stat.S_ISREG(st.st_mode):
        raise ApprovalError("approval store is not a plain file (symlink/directory refused)")
    if st.st_mode & 0o022:
        raise ApprovalError("approval store is group/world writable")
    if st.st_size == 0:
        raise ApprovalError("approval store is empty")
    if st.st_size > MAX_STORE_BYTES:
        raise ApprovalError("approval store too large")
    real = os.path.realpath(path)
    for root in forbidden_roots:
        root = os.path.realpath(root)
        if real == root or real.startswith(root.rstrip("/") + "/"):
            raise ApprovalError(f"approval store lies inside a caller-reachable tree ({root}): self-pinned authority refused")
    if any(os.path.normpath(os.fspath(f)) in (real, os.path.normpath(path)) for f in forbidden_files):   # string compare only
        raise ApprovalError("approval store is a caller-supplied file: self-pinned authority refused")
    with open(path, "rb") as fh:
        data = fh.read(MAX_STORE_BYTES + 1)
    if len(data) != st.st_size:
        raise ApprovalError("approval store changed while reading")
    return data


def check_approval(store_bytes, *, record_sha256: str, issuer: str, execution_id: str, provenance_approval_id: str,
                   provenance_receipt_sha256: str, authorization_sha256: str) -> dict:
    """Pure. The store must be wholly well formed; exactly one entry must bind this record hash, and every other field of that
    entry must equal the live/derived value. Returns the matching entry."""
    if not isinstance(store_bytes, (bytes, bytearray)) or not store_bytes:
        raise ApprovalError("approval store missing or empty")
    try:
        store = json.loads(store_bytes)
    except ValueError as exc:
        raise ApprovalError(f"approval store is not valid JSON: {exc}") from None
    if not isinstance(store, dict) or set(store) != _STORE_KEYS or store["schema"] != STORE_SCHEMA:
        raise ApprovalError(f"approval store must have exactly keys {sorted(_STORE_KEYS)} and schema {STORE_SCHEMA}")
    entries = store["approvals"]
    if not isinstance(entries, list) or not entries:
        raise ApprovalError("approval store holds no approvals")
    seen = set()
    for e in entries:
        if not isinstance(e, dict) or set(e) != _ENTRY_KEYS:
            raise ApprovalError(f"approval entry keys must be exactly {sorted(_ENTRY_KEYS)}")
        for key in ("approval_id", "issuer", "execution_id", "provenance_approval_id"):
            if not isinstance(e[key], str) or not e[key].strip():
                raise ApprovalError(f"approval entry {key} missing")
        for key in ("record_sha256", "provenance_receipt_sha256"):
            if not _is_sha(e[key]):
                raise ApprovalError(f"approval entry {key} malformed")
        if e["release_scope"] != REAL_SCOPE:
            raise ApprovalError(f"approval entry release_scope must be {REAL_SCOPE}")
        if e["record_sha256"] in seen:
            raise ApprovalError("approval store binds one record hash twice")
        seen.add(e["record_sha256"])
    match = [e for e in entries if e["record_sha256"] == record_sha256]
    if not match:
        raise ApprovalError("no Director approval binds this exact release record sha256")
    e = match[0]
    if e["issuer"] != issuer:
        raise ApprovalError("approval issuer differs from the record issuer")
    if e["execution_id"] != execution_id:
        raise ApprovalError("approval execution_id differs from the live execution id")
    if e["provenance_approval_id"] != provenance_approval_id:
        raise ApprovalError("approval provenance_approval_id differs from the authorization provenance")
    if not _is_sha(provenance_receipt_sha256) or e["provenance_receipt_sha256"] != provenance_receipt_sha256:
        raise ApprovalError("provenance acceptance receipt sha256 differs from the approval (bad/missing provenance approval)")
    if provenance_receipt_sha256 in (record_sha256, authorization_sha256):
        raise ApprovalError("provenance receipt sha256 is self-derived from the record/authorization, not an external receipt")
    return dict(e)


def store_sha256(store_bytes: bytes) -> str:
    return hashlib.sha256(store_bytes).hexdigest()
