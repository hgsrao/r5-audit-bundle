"""Director-review fixes. UNIT VERIFICATION on SYNTHETIC generated fixtures only; no market data is read or replayed.

Covers: exact physical read cap (cap not a chunk multiple), per-file read plans, full authorization binding, wrong root /
wrong content / wrong boundary, no data open on invalid authorization, preTRAIN vs TRAIN modelling, the OS-isolation gate.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import importlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

PLATFORM = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
SNAPSHOT = PLATFORM / "snapshot"
sys.dont_write_bytecode = True
sys.path.insert(0, str(PLATFORM / "harness"))
sys.path.insert(0, str(PLATFORM / "harness_tests"))

import synth  # noqa: E402
import wp004_train_harness as h  # noqa: E402

h.verify_snapshot(SNAPSHOT)
h.activate_snapshot(SNAPSHOT)

CONTRACT_SHA = "c" * 64


# ------------------------------------------------------------------ witnesses
class FileWitness:
    """Independent FileIO-level witness: wraps builtins.open for files under ``roots`` and logs open/seek/read."""

    def __init__(self, monkeypatch, roots):
        self.roots = [Path(r).resolve() for r in roots]
        self.events = []
        witness, real = self, builtins.open

        class Wrap:
            def __init__(self, handle, key):
                self.handle, self.key = handle, key

            def read(self, n=-1):
                before = self.handle.tell()
                data = self.handle.read(n)
                witness.events.append(("read", self.key, before, n, len(data)))
                return data

            def seek(self, pos, whence=0):
                witness.events.append(("seek", self.key, pos))
                return self.handle.seek(pos, whence)

            def tell(self):
                return self.handle.tell()

            def close(self):
                self.handle.close()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        def opener(file, mode="r", *a, **k):
            if isinstance(file, (str, os.PathLike)):
                resolved = Path(file).resolve()
                if any(resolved == r or resolved.is_relative_to(r) for r in witness.roots):
                    witness.events.append(("open", str(resolved)))
                    if "b" in mode and "r" in mode:
                        return Wrap(real(file, mode, *a, **k), str(resolved))
            return real(file, mode, *a, **k)
        monkeypatch.setattr(builtins, "open", opener)

    @property
    def opened(self):
        return [e[1] for e in self.events if e[0] == "open"]

    def reads(self, key=None):
        return [e for e in self.events if e[0] == "read" and (key is None or e[1] == key)]

    def bytes_read(self, key=None):
        return sum(e[4] for e in self.reads(key))

    def byte_ranges(self, key):
        return [(e[2], e[2] + e[4]) for e in self.reads(key) if e[4]]


# --------------------------------------------------------------------- 1. exact cap
def lines_file(tmp_path, n=200, width=10):
    p = tmp_path / "f.csv"
    p.write_bytes(b"".join((b"%0*d\n" % (width - 1, i)) for i in range(n)))
    return p


@pytest.mark.parametrize("cap,chunk", [(105, 64), (100, 64), (64, 64), (63, 64), (1, 64), (65, 64), (257, 100), (11, 4096)])
def test_cap_never_overshoots_even_when_not_chunk_multiple(tmp_path, monkeypatch, cap, chunk):
    p = lines_file(tmp_path)
    wit = FileWitness(monkeypatch, [tmp_path])
    r = h.BoundedLineReader(p, chunk_size=chunk, max_physical_bytes=cap)
    got = 0
    with pytest.raises(h.ReadBoundaryError, match="physical read cap"):
        while r.next_line() is not None:
            got += 1
    r.close()
    key = str(p.resolve())
    assert wit.bytes_read(key) == cap                                   # independent witness: exactly the cap, never more
    assert r.physical_bytes_read == cap
    assert all(e[3] <= cap for e in wit.reads(key)) and all(e[4] <= chunk for e in wit.reads(key))
    assert got == cap // 10                                              # only complete lines inside the cap were served
    calls = len(wit.reads(key))
    r2 = h.BoundedLineReader(p, chunk_size=chunk, max_physical_bytes=cap)
    r2.close()
    assert len(wit.reads(key)) == calls                                  # constructing/closing performs no read


def test_cap_attempt_beyond_fails_before_the_prohibited_byte(tmp_path, monkeypatch):
    p = lines_file(tmp_path)
    wit = FileWitness(monkeypatch, [tmp_path])
    r = h.BoundedLineReader(p, chunk_size=64, max_physical_bytes=105)
    for _ in range(10):
        r.next_line()
    key = str(p.resolve())
    calls = len(wit.reads(key))
    for _ in range(3):                                                   # repeated attempts beyond the cap
        with pytest.raises(h.ReadBoundaryError, match="physical read cap 105"):
            r.next_line()
    assert len(wit.reads(key)) == calls and wit.bytes_read(key) == 105   # no read call was even issued
    r.close()


def test_cap_exactly_equal_to_consumed_boundary_is_allowed(tmp_path, monkeypatch):
    p = lines_file(tmp_path)
    wit = FileWitness(monkeypatch, [tmp_path])
    r = h.BoundedLineReader(p, chunk_size=64, max_physical_bytes=100)
    assert [r.next_line() for _ in range(10)][-1] == b"000000009\n"
    assert wit.bytes_read(str(p.resolve())) == 100
    rec = r.record(strict_prefix=True)
    assert rec["physical_bytes_read"] == 100 == rec["consumed_bytes"] and rec["max_physical_bytes"] == 100
    r.close()


@pytest.mark.parametrize("bad", [True, False, 0, -5, 1.5, "10", None.__class__])
def test_cap_and_chunk_validation_before_open(tmp_path, monkeypatch, bad):
    p = lines_file(tmp_path)
    wit = FileWitness(monkeypatch, [tmp_path])
    with pytest.raises(h.HarnessError):
        h.BoundedLineReader(p, chunk_size=bad)
    with pytest.raises(h.HarnessError):
        h.BoundedLineReader(p, chunk_size=64, max_physical_bytes=bad)
    assert wit.events == []                                              # nothing opened, nothing read
    with pytest.raises(h.HarnessError):
        h.HarnessConfig(snapshot_dir=SNAPSHOT, allowed_manifest_roots=(), allowed_data_roots=(), allowed_grid_roots=(),
                        output_root=tmp_path, chunk_size=bad)


def test_cap_enforced_in_prepare_end_to_end_with_witness(tmp_path, monkeypatch):
    w = synth.World(tmp_path / "w")
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    cap = 1001                                                           # not a multiple of the chunk
    prepare = h.make_prepare(base_cfg(w, chunk_size=512, max_physical_bytes_per_file=cap), h.ReadLedger())
    with pytest.raises(h.ReadBoundaryError, match="physical read cap 1001"):
        prepare(w.root, w.protocol, w.block)
    assert wit.reads() and all(wit.bytes_read(k) <= cap for k in {e[1] for e in wit.reads()})


# ------------------------------------------------------------------- 2. read plans
def test_plan_reader_reads_only_authorized_ranges_and_never_beyond(tmp_path, monkeypatch):
    p = lines_file(tmp_path)
    wit = FileWitness(monkeypatch, [tmp_path])
    ivs = [(0, 20, "HEADER"), (100, 130, "TRAIN_DATA")]
    r = h.BoundedLineReader(p, chunk_size=7, intervals=ivs)
    lines = []
    with pytest.raises(h.ReadBoundaryError, match="authorized read plan exhausted"):
        while True:
            lines.append(r.next_line())
    key = str(p.resolve())
    assert len(lines) == 5 and r.physical_bytes_read == 50
    ranges = wit.byte_ranges(key)
    assert all((s, e) in [(0, 20), (100, 130)] or (0 <= s and e <= 20) or (100 <= s and e <= 130) for s, e in ranges)
    assert wit.bytes_read(key) == 50 and ("seek", key, 100) in wit.events
    assert max(e for _, e in ranges) == 130
    r.close()


def test_plan_reader_rejects_straddle_bad_intervals_and_file_shorter(tmp_path):
    p = lines_file(tmp_path)
    r = h.BoundedLineReader(p, chunk_size=7, intervals=[(0, 15, "HEADER"), (100, 130, "TRAIN_DATA")])
    r.next_line()
    with pytest.raises(h.ReadBoundaryError, match="straddles"):
        r.next_line()
    r.close()
    for bad in ([], [(5, 5, "HEADER")], [(10, 20, "HEADER"), (15, 30, "TRAIN_DATA")], [(0, 5, "NOPE")],
                [(True, 5, "HEADER")], [(0, 1.5, "HEADER")]):
        with pytest.raises(h.ReadBoundaryError):
            h.BoundedLineReader(p, intervals=bad)
    with pytest.raises(h.ReadBoundaryError, match="beyond file size"):
        h.BoundedLineReader(p, intervals=[(0, 10_000, "HEADER")])


# ---------------------------------------------------------- authorization fixtures
def base_cfg(w, **kw):
    base = dict(snapshot_dir=SNAPSHOT, allowed_manifest_roots=(w.root,), allowed_data_roots=(w.data,),
                allowed_grid_roots=(w.grid,), output_root=w.base / "out", chunk_size=4096)
    base.update(kw)
    return h.HarnessConfig(**base)


def row_offsets(data):
    offs = [0]
    for line in data.splitlines(keepends=True):
        offs.append(offs[-1] + len(line))
    return offs                                   # offs[1 + k] = start of data row k; offs[1] = header end


def sha(b):
    return hashlib.sha256(b).hexdigest()


def baseline_grid_ends(w):
    """Mechanics-only: take the grid boundary end from an unplanned synthetic run (a REAL run needs external evidence)."""
    ledger = h.ReadLedger()
    h.make_prepare(base_cfg(w, pretrain_policy="WARMUP_PROVENANCE_NO_FIT"), ledger)(w.root, w.protocol, w.block)
    return {Path(r["path"]).name: r["consumed_bytes"] for r in ledger.files if r["role"] == "grid"}


def file_entry(role, name, path, data, segments, *, tag="x"):
    """segments: [(start_offset, end_offset, kind)] after the HEADER; commitment is over the exact permitted bytes."""
    offs = row_offsets(data)
    ivs = [(0, offs[1], "HEADER")] + list(segments)
    permitted = b"".join(data[s:e] for s, e, _ in ivs)
    return {"role": role, "name": name, "canonical_path": str(Path(path).resolve()),
            "intervals": [{"start": s, "end": e, "kind": k} for s, e, k in ivs],
            "max_physical_bytes": len(permitted), "content_commitment_sha256": sha(permitted),
            "provenance_id": f"synthetic-acquisition-{tag}-{name}",
            "boundary_evidence": {"schema": h.BOUNDARY_EVIDENCE_SCHEMA, "evidence_id": f"ev-{name}",
                                  "evidence_artifact_sha256": sha(f"ev-{name}".encode()), "issuer": "synthetic-independent-issuer",
                                  "independent_of_harness": True, "file_size_bytes_at_audit": len(data)},
            "terminal_boundary_row_authorized": True}


def build_auth(w, *, policy="REJECT", skip_rows=0, stock_segments=None):
    ends = baseline_grid_ends(w)
    files = []
    for sym in w.symbols:
        data = w.csv_path(sym).read_bytes()
        offs = row_offsets(data)
        send = w.offsets(sym)["sentinel_end"]
        segs = stock_segments(sym, data, offs, send) if stock_segments else [(offs[1 + skip_rows], send, "TRAIN_DATA")]
        files.append(file_entry("stock", sym, w.csv_path(sym), data, segs))
    for name in synth.GRID_NAMES:
        path = w.grid / f"{name}.csv"
        data = path.read_bytes()
        offs = row_offsets(data)
        files.append(file_entry("grid", name, path, data, [(offs[1], ends[path.name], "TRAIN_DATA")]))
    return {"schema": h.AUTH_SCHEMA, "execution_package_id": "SYNTH-PKG-1", "contract_id": h.CONTRACT_ID,
            "contract_sha256": CONTRACT_SHA, "classification": h.CLASSIFICATION, "authorizes_real_data_read": True,
            "pins": {"snapshot_manifest_sha256": "1" * 64, "protocol_sha256": "2" * 64, "params_sha256": "3" * 64,
                     "snapshot_head": h.EXPECTED_HEAD},
            "roots": {"manifest_root": str(w.root), "data_root": str(w.data), "grid_root": str(w.grid),
                      "output_root": str(w.base / "out"), "output_dir": str(w.base / "out" / "run")},
            "stage_b": {"block": 1, "sessions": list(w.sessions)}, "risk_scope": h.RISK_SCOPE, "cnc_runtime": h.CNC_STATE,
            "pretrain_policy": policy, "commitment_scope": h.COMMITMENT_SCOPE, "files": files}


def bindings_for(w, **ov):
    b = dict(contract_sha256=CONTRACT_SHA, snapshot_manifest_sha256="1" * 64, protocol_sha256="2" * 64,
             params_sha256="3" * 64, manifest_root=w.root, data_root=w.data, grid_root=w.grid,
             output_root=w.base / "out", output_dir=w.base / "out" / "run")
    b.update(ov)
    return b


def validate(w, auth, **kw):
    raw = json.dumps(auth).encode()
    return h.validate_real_authorization(raw, authorization_sha256_pin=kw.pop("pin", sha(raw)), protocol=w.protocol,
                                         bindings=bindings_for(w, **kw))


def real_config(w, plan, **kw):
    return base_cfg(w, read_plan=plan, real_execution=True, pretrain_policy=plan.pretrain_policy, **kw)


@pytest.fixture
def gate_open(monkeypatch):
    """Test-only: lets the downstream plan enforcement run on synthetic data. The shipped gate always refuses."""
    monkeypatch.setattr(h, "os_isolation_witness", lambda: {"test_only_stub": True})


# ----------------------------------------------- 3. valid plan, exact consumption, e2e
@pytest.mark.parametrize("skip_rows", [0, 50])   # 50: first 50 data rows skipped => non-contiguous intervals + seek
def test_valid_authorization_runs_exactly_inside_plan(tmp_path, monkeypatch, gate_open, skip_rows):
    w = synth.World(tmp_path / "w")
    plan = validate(w, build_auth(w, skip_rows=skip_rows))
    before = {p.name: sha(p.read_bytes()) for p in list(w.data.iterdir()) + list(w.grid.iterdir())}
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    result, receipt = h.run_block_diagnostic(real_config(w, plan), w.root, w.protocol, w.block, {}, w.base / "out" / "run")
    assert receipt["real_execution"] is True and receipt["os_isolation_witness"] == {"test_only_stub": True}
    assert "do not prove native/system IO" in receipt["python_tripwire_limits"]
    assert receipt["authorization"]["commitment_scope"] == h.COMMITMENT_SCOPE
    assert "not historical sealed membership" in receipt["authorization"]["commitment_disclosure"]
    assert receipt["authorization"]["authorization_sha256"] == plan.authorization_sha256
    assert receipt["tripwire"]["zero_access"] and receipt["combined_cycle_runtime"] is None
    for row in receipt["read_files"]:
        fp = plan.files[row["path"]]
        ranges = wit.byte_ranges(row["path"])
        assert wit.bytes_read(row["path"]) == fp.max_physical_bytes == row["physical_bytes_read"] == row["consumed_bytes"]
        assert all(any(s <= a and b <= e for s, e, _ in fp.intervals) for a, b in ranges)   # every read inside an interval
        assert row["content_commitment_verified"] and row["provenance_id"] == fp.provenance_id
        assert row["physical_bytes_read"] < row["size_bytes"]
    for name, audit in result["audit"]["grid"].items():
        assert audit["boundary_row_authorized"] is True and audit["boundary_rows_parsed_and_discarded"] == 1
        assert audit["boundary_row_affects_retained_feed"] is False and audit["rows_after_cutoff_retained"] == 0
        assert audit["train_scope"] == h.TRAIN_SCOPE_DISCLOSURE
    for audit in result["audit"]["stock"].values():
        assert audit["sentinel_row_authorized"] is True and audit["pretrain_rows_consumed"] == 0
    assert before == {p.name: sha(p.read_bytes()) for p in list(w.data.iterdir()) + list(w.grid.iterdir())}
    # same frames as the unplanned bounded run (planned run only restricts WHICH bytes are read)
    (ref_frames, ref_feeds, _), _ = (h.make_prepare(base_cfg(w), h.ReadLedger())(w.root, w.protocol, w.block), None)
    prepare = h.make_prepare(real_config(w, plan), h.ReadLedger())
    frames, feeds, _ = prepare(w.root, w.protocol, w.block)
    for sym in ref_frames:
        pd.testing.assert_frame_equal(ref_frames[sym].iloc[-frames[sym].shape[0]:].reset_index(drop=True),
                                      frames[sym].reset_index(drop=True))
    for name in ref_feeds:
        pd.testing.assert_frame_equal(ref_feeds[name], feeds[name])


def test_real_config_without_plan_fails_closed(tmp_path):
    w = synth.World(tmp_path / "w")
    with pytest.raises(h.AuthorizationError):
        h.HarnessConfig(snapshot_dir=SNAPSHOT, allowed_manifest_roots=(w.root,), allowed_data_roots=(w.data,),
                        allowed_grid_roots=(w.grid,), output_root=w.base / "out", real_execution=True)


# ------------------------------------- 4. authorization binding; no data open on invalid authorization
def mut(path, value):
    def apply(auth):
        node = auth
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return apply


def drop(path):
    def apply(auth):
        node = auth
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return apply


F0 = ("files", 0)
AUTH_MUTATIONS = {
    "schema": mut(["schema"], "OTHER"), "contract_id": mut(["contract_id"], "OTHER"),
    "contract_sha": mut(["contract_sha256"], "d" * 64), "classification": mut(["classification"], "SEALED"),
    "authorizes_false": mut(["authorizes_real_data_read"], False), "authorizes_truthy": mut(["authorizes_real_data_read"], 1),
    "risk_scope": mut(["risk_scope"], "LOOSENED"), "cnc_enabled": mut(["cnc_runtime"], "ENABLED"),
    "commitment_scope": mut(["commitment_scope"], "HISTORICAL_SEALED"),
    "pin_snapshot": mut(["pins", "snapshot_manifest_sha256"], "9" * 64), "pin_protocol": mut(["pins", "protocol_sha256"], "9" * 64),
    "pin_params": mut(["pins", "params_sha256"], "9" * 64), "pin_head": mut(["pins", "snapshot_head"], "0" * 40),
    "root_manifest": mut(["roots", "manifest_root"], "/tmp/elsewhere"), "root_data": mut(["roots", "data_root"], "/tmp/elsewhere"),
    "root_grid": mut(["roots", "grid_root"], "/tmp/elsewhere"), "root_output": mut(["roots", "output_root"], "/tmp/elsewhere"),
    "output_dir": mut(["roots", "output_dir"], "/tmp/elsewhere/run"),
    "block": mut(["stage_b", "block"], 2), "sessions": mut(["stage_b", "sessions"], ["2030-01-01"]),
    "pretrain_policy": mut(["pretrain_policy"], "ALLOW"), "package_id": mut(["execution_package_id"], " "),
    "bypass_key_os": mut(["os_isolation_ok"], True), "bypass_key_gate": mut(["bypass_os_gate"], True),
    "missing_key": drop(["risk_scope"]), "missing_files": mut(["files"], []),
    "file_path_outside": mut(["files", 0, "canonical_path"], "/tmp/other.csv"),
    "file_path_relative": mut(["files", 0, "canonical_path"], "x.csv"),
    "file_path_dotdot": mut(["files", 0, "canonical_path"], "/tmp/../x.csv"),
    "file_cap_bool": mut(["files", 0, "max_physical_bytes"], True),
    "file_cap_mismatch": mut(["files", 0, "max_physical_bytes"], 10**9),
    "file_commit_bad": mut(["files", 0, "content_commitment_sha256"], "xyz"),
    "file_prov_empty": mut(["files", 0, "provenance_id"], ""), "file_prov_missing": drop(["files", 0, "provenance_id"]),
    "file_evidence_missing": drop(["files", 0, "boundary_evidence"]),
    "file_evidence_indep_false": mut(["files", 0, "boundary_evidence", "independent_of_harness"], False),
    "file_evidence_schema": mut(["files", 0, "boundary_evidence", "schema"], "X"),
    "file_boundary_row_unauthorized": mut(["files", 0, "terminal_boundary_row_authorized"], False),
    "file_header_not_zero": mut(["files", 0, "intervals", 0, "start"], 1),
    "file_kind_unknown": mut(["files", 0, "intervals", 1, "kind"], "ALL"),
    "file_extra_key": mut(["files", 0, "skip_checks"], True),
    "file_role": mut(["files", 0, "role"], "other"),
}


@pytest.mark.parametrize("name", sorted(AUTH_MUTATIONS))
def test_authorization_mismatch_refused_before_any_data_open(tmp_path, monkeypatch, name):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w)
    AUTH_MUTATIONS[name](auth)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.AuthorizationError):
        validate(w, auth)
    assert wit.events == []


def test_authorization_sha_pin_and_bound_bindings(tmp_path, monkeypatch):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.AuthorizationError, match="differs from pin"):
        validate(w, auth, pin="0" * 64)
    with pytest.raises(h.AuthorizationError, match="malformed"):
        validate(w, auth, pin="nothex")
    raw = b"{not json"
    with pytest.raises(h.AuthorizationError, match="JSON"):
        h.validate_real_authorization(raw, authorization_sha256_pin=sha(raw), protocol=w.protocol, bindings=bindings_for(w))
    for key, bad in (("contract_sha256", "e" * 64), ("snapshot_manifest_sha256", "e" * 64), ("protocol_sha256", "e" * 64),
                     ("params_sha256", "e" * 64), ("data_root", w.base / "nope"), ("grid_root", w.base / "nope"),
                     ("manifest_root", w.base / "nope"), ("output_root", w.base / "nope"), ("output_dir", w.base / "out" / "other")):
        with pytest.raises(h.AuthorizationError):
            validate(w, auth, **{key: bad})                     # supplied binding differs from what the file authorizes
    assert validate(w, auth).authorization_sha256 == sha(json.dumps(auth).encode())
    assert wit.events == []


def test_wrong_root_symlink_and_foreign_file_cannot_enter_plan_or_open(tmp_path, monkeypatch):
    w = synth.World(tmp_path / "w")
    other = synth.World(tmp_path / "other")
    auth = build_auth(w)
    auth["files"][0] = build_auth(other)["files"][0]            # a perfectly formed entry from a DIFFERENT data root
    wit = FileWitness(monkeypatch, [w.data, w.grid, other.data, other.grid])
    with pytest.raises(h.AuthorizationError, match="outside the declared"):
        validate(w, auth)
    assert wit.events == []


@pytest.mark.parametrize("case", ["missing_file", "extra_file", "size_vs_evidence", "interval_to_eof", "renamed_path"])
def test_plan_vs_metadata_mismatch_refused_before_first_data_open(tmp_path, monkeypatch, gate_open, case):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w)
    if case == "missing_file":
        auth["files"].pop(0)
    elif case == "extra_file":
        extra = w.data / "EXTRA.csv"
        extra.write_bytes(w.csv_path(w.symbols[0]).read_bytes())
        data = extra.read_bytes()
        auth["files"].append(file_entry("stock", "EXTRA", extra, data, [(row_offsets(data)[1], 500, "TRAIN_DATA")]))
    elif case == "size_vs_evidence":
        auth["files"][0]["boundary_evidence"]["file_size_bytes_at_audit"] += 1
    elif case == "interval_to_eof":
        data = w.csv_path(w.symbols[0]).read_bytes()
        auth["files"][0] = file_entry("stock", w.symbols[0], w.csv_path(w.symbols[0]), data, [(row_offsets(data)[1], len(data), "TRAIN_DATA")])
    elif case == "renamed_path":
        auth["files"][0]["name"] = "ZZZ"
    plan = validate(w, auth)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.AuthorizationError):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
    assert wit.opened == []                                    # whole plan validated before the first data file opened
    with pytest.raises(h.AuthorizationError):
        h.run_block_diagnostic(real_config(w, plan), w.root, w.protocol, w.block, {}, w.base / "out" / "run")
    assert wit.opened == []


def test_invalid_grid_metadata_with_plan_refused_before_stock_files_open(tmp_path, monkeypatch, gate_open):
    w = synth.World(tmp_path / "w")
    plan = validate(w, build_auth(w))
    w.protocol["grid_dataset"]["feeds"]["NIFTY_50_15MIN"]["sha256"] = "f" * 64
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(ValueError, match="SHA mismatch"):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
    assert wit.opened == []


# ----------------------------------------------- 5. wrong content / wrong boundary proof
def test_content_commitment_verified_on_consumed_bytes(tmp_path, monkeypatch, gate_open):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w)
    sym = w.symbols[0]
    path = w.csv_path(sym)
    blob = bytearray(path.read_bytes())
    first_target = row_offsets(bytes(blob))[2] - 2            # last digit of the first row's volume (inside the prefix)
    blob[first_target] = ord("7") if blob[first_target] != ord("7") else ord("8")     # same size, edit INSIDE the prefix
    path.write_bytes(bytes(blob))
    plan = validate(w, auth)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.ContentCommitmentError, match="do not match"):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
    for key in {e[1] for e in wit.reads()}:
        assert wit.bytes_read(key) <= plan.files[key].max_physical_bytes      # even the failing run never exceeded the plan


def test_tail_edit_beyond_boundary_is_not_read_or_detected(tmp_path, gate_open):
    w = synth.World(tmp_path / "w")
    plan = validate(w, build_auth(w))
    path = w.csv_path(w.symbols[0])
    blob = path.read_bytes()
    path.write_bytes(blob[:-30] + b"X" * 30)
    h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)   # same size, outside permitted bytes
    assert path.stat().st_size == len(blob)


def test_wrong_commitment_value_refused_after_only_planned_bytes(tmp_path, monkeypatch, gate_open):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w)
    auth["files"][0]["content_commitment_sha256"] = "a" * 64
    plan = validate(w, auth)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.ContentCommitmentError):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
    assert wit.bytes_read(auth["files"][0]["canonical_path"]) == auth["files"][0]["max_physical_bytes"]


def test_wrong_boundary_proof_earlier_or_later_than_sentinel(tmp_path, monkeypatch, gate_open):
    for shift, expected in ((-1, "authorized read plan exhausted"), (+1, "not exactly consumed")):
        w = synth.World(tmp_path / f"w{shift}")
        sym = w.symbols[0]

        def segs(s, data, offs, send, _sym=sym, _shift=shift):
            if s != _sym:
                return [(offs[1], send, "TRAIN_DATA")]
            end = offs[offs.index(send) + _shift] if _shift > 0 else offs[offs.index(send) + _shift]
            return [(offs[1], end, "TRAIN_DATA")]
        plan = validate(w, build_auth(w, stock_segments=segs))
        wit = FileWitness(monkeypatch, [w.data, w.grid])
        with pytest.raises(h.ReadBoundaryError, match=expected):
            h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
        path = str(w.csv_path(sym).resolve())
        assert wit.bytes_read(path) <= plan.files[path].max_physical_bytes     # boundary proof was wrong; bytes still capped
        monkeypatch.undo()


def test_unplanned_harness_open_trips_the_guard(tmp_path):
    w = synth.World(tmp_path / "w")
    plan = validate(w, build_auth(w))
    stray = w.data / "STRAY.csv"
    stray.write_bytes(b"a,b\n1,2\n")
    with h.Tripwire(forbidden_read_roots=[w.data, w.grid], planned_paths=plan.files) as tw:
        with pytest.raises(h.TripwireViolation, match="unplanned_harness_open"):
            h.BoundedLineReader(stray, chunk_size=16)
        h.BoundedLineReader(w.csv_path(w.symbols[0]), chunk_size=16).close()        # planned path is fine
    assert tw.report()["zero_access"] is False
    with pytest.raises(h.UnplannedFileError):
        plan.require(stray)


# ------------------------------------- 6. preTRAIN vs retained TRAIN rows; boundary rows
def pretrain_world(tmp_path, name="w"):
    w = synth.World(tmp_path / name, grid_start=date(2023, 12, 1))
    w.protocol["periods"]["train_start"] = "2023-12-01"      # days 11-29 and 11-30 (80 rows) are now preTRAIN
    return w


def pretrain_segments(sym, data, offs, send):
    # data rows 0..79 are preTRAIN; 60-bar warmup needs data rows 60..119; target+sentinel follow.
    return [(offs[1 + 60], offs[1 + 80], "PRETRAIN_WARMUP_NO_FIT"), (offs[1 + 80], send, "TRAIN_DATA")]


def test_pretrain_selection_rejected_by_default_without_authorization(tmp_path):
    w = pretrain_world(tmp_path)
    with pytest.raises(h.PreTrainSelectionError, match="not authorized"):
        h.make_prepare(base_cfg(w), h.ReadLedger())(w.root, w.protocol, w.block)


def test_pretrain_warmup_allowed_only_when_separately_authorized_and_disclosed(tmp_path):
    w = pretrain_world(tmp_path)
    (frames, feeds, audit), ledger = h.make_prepare(base_cfg(w, pretrain_policy="WARMUP_PROVENANCE_NO_FIT"),
                                                    h.ReadLedger())(w.root, w.protocol, w.block), None
    a = audit["stock"][w.symbols[0]]
    assert a["pretrain_policy"] == "WARMUP_PROVENANCE_NO_FIT" and a["pretrain_rows_consumed"] == 80
    assert a["warmup_rows_dated_before_train_start"] == 20 and a["train_scope"] == h.TRAIN_SCOPE_DISCLOSURE
    assert "never inferred from timestamps" in a["train_scope"]


def test_pretrain_plan_rules(tmp_path, gate_open):
    w = pretrain_world(tmp_path)
    with pytest.raises(h.AuthorizationError, match="preTRAIN interval present"):
        validate(w, build_auth(w, policy="REJECT", stock_segments=pretrain_segments))
    plan = validate(w, build_auth(w, policy="WARMUP_PROVENANCE_NO_FIT", stock_segments=pretrain_segments))
    frames, feeds, audit = h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)
    a = audit["stock"][w.symbols[0]]
    assert a["pretrain_rows_consumed"] == 20 and a["warmup_rows_dated_before_train_start"] == 20
    # mislabelled: preTRAIN-dated rows inside a TRAIN_DATA interval, then TRAIN rows inside a PRETRAIN interval
    plan = validate(w, build_auth(w, policy="REJECT"))
    with pytest.raises(h.PreTrainSelectionError):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)

    def wrong_label(sym, data, offs, send):
        return [(offs[1 + 60], offs[1 + 90], "PRETRAIN_WARMUP_NO_FIT"), (offs[1 + 90], send, "TRAIN_DATA")]
    plan = validate(w, build_auth(w, policy="WARMUP_PROVENANCE_NO_FIT", stock_segments=wrong_label))
    with pytest.raises(h.PreTrainSelectionError, match="inside a PRETRAIN interval"):
        h.make_prepare(real_config(w, plan), h.ReadLedger())(w.root, w.protocol, w.block)


def test_pretrain_grid_rows_never_enter_retained_feeds(tmp_path):
    w = synth.World(tmp_path / "w")
    w.protocol["periods"]["train_start"] = "2023-11-23"      # grid starts 2023-11-22 => first day is preTRAIN
    for policy in ("REJECT", "WARMUP_PROVENANCE_NO_FIT"):
        with pytest.raises(h.PreTrainSelectionError, match="preTRAIN grid row"):
            h.make_prepare(base_cfg(w, pretrain_policy=policy), h.ReadLedger())(w.root, w.protocol, w.block)


def test_pretrain_interval_refused_for_grid_files(tmp_path):
    w = synth.World(tmp_path / "w")
    auth = build_auth(w, policy="WARMUP_PROVENANCE_NO_FIT")
    grid = next(f for f in auth["files"] if f["role"] == "grid")
    grid["intervals"][1]["kind"] = "PRETRAIN_WARMUP_NO_FIT"
    with pytest.raises(h.AuthorizationError, match="never authorized for grid"):
        validate(w, auth)


def test_external_boundary_evidence_schema_is_required_not_generated():
    schema = h.REQUIRED_EXTERNAL_BOUNDARY_EVIDENCE_SCHEMA
    assert set(schema) == {"schema", "evidence_id", "evidence_artifact_sha256", "issuer", "independent_of_harness",
                           "file_size_bytes_at_audit"} and schema["schema"] == h.BOUNDARY_EVIDENCE_SCHEMA
    public = [n for n in dir(h) if "evidence" in n.lower() and callable(getattr(h, n))]
    assert public == []                                    # no function produces boundary evidence


# ------------------------------------------------- 7. OS gate / runner
def test_os_gate_always_refuses_and_is_not_a_json_field():
    assert h.OS_ISOLATION_WITNESS_IMPLEMENTED is False
    with pytest.raises(h.IsolationGateError, match="OS-level"):
        h.os_isolation_witness()
    assert "os" not in " ".join(h._AUTH_KEYS | h._PIN_KEYS | h._ROOT_KEYS | h._FILE_KEYS).replace("roots", "")


def test_real_execution_refused_at_gate_before_any_open(tmp_path, monkeypatch):
    w = synth.World(tmp_path / "w")
    plan = validate(w, build_auth(w))
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.IsolationGateError):
        h.run_block_diagnostic(real_config(w, plan), w.root, w.protocol, w.block, {}, w.base / "out" / "run")
    assert wit.events == [] and not (w.base / "out" / "run").exists()


def runner_argv(w, auth, tmp_path, protocol_path, *, auth_sha=None):
    contract = tmp_path / "contract.md"
    contract.write_text("synthetic contract stand-in\n")
    params = tmp_path / "params.json"
    params.write_text("{}")
    auth["contract_sha256"] = sha(contract.read_bytes())
    auth["pins"].update(snapshot_manifest_sha256=h.sha256_code_file(PLATFORM / "SNAPSHOT_MANIFEST.json"),
                        protocol_sha256=sha(protocol_path.read_bytes()), params_sha256=sha(params.read_bytes()))
    ap = tmp_path / "auth.json"
    ap.write_text(json.dumps(auth))
    return ["--authorization", str(ap), "--authorization-sha256", auth_sha or sha(ap.read_bytes()),
            "--contract-file", str(contract), "--snapshot-manifest-sha256", auth["pins"]["snapshot_manifest_sha256"],
            "--protocol", str(protocol_path), "--protocol-sha256", auth["pins"]["protocol_sha256"],
            "--params-json", str(params), "--params-sha256", auth["pins"]["params_sha256"], "--root", str(w.root),
            "--data-root", str(w.data), "--grid-root", str(w.grid), "--output-root", str(w.base / "out"),
            "--output-dir", str(w.base / "out" / "run"), "--chunk-size", "4096"]


def test_runner_valid_authorization_still_refused_by_os_gate_without_touching_data(tmp_path, monkeypatch):
    import run_nonsealed_diagnostic as runner
    w = synth.World(tmp_path / "w")
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(w.protocol))
    argv = runner_argv(w, build_auth(w), tmp_path, protocol_path)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(SystemExit, match="REFUSED.*OS-level"):
        runner.main(argv)
    assert wit.events == [] and not (w.base / "out" / "run").exists()


def test_runner_invalid_authorization_refused_without_touching_data(tmp_path, monkeypatch):
    import run_nonsealed_diagnostic as runner
    w = synth.World(tmp_path / "w")
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(w.protocol))
    auth = build_auth(w)
    auth["files"][0]["terminal_boundary_row_authorized"] = False
    good_auth = build_auth(w)                                  # fixture construction reads files: do it BEFORE the witness
    argv = runner_argv(w, auth, tmp_path, protocol_path)
    wit = FileWitness(monkeypatch, [w.data, w.grid])
    with pytest.raises(SystemExit, match="REFUSED.*boundary row"):
        runner.main(argv)
    assert wit.events == []
    good =runner_argv(w, good_auth, tmp_path, protocol_path, auth_sha="0" * 64)
    with pytest.raises(SystemExit, match="REFUSED.*differs from pin"):
        runner.main(good)
    bad_root = list(good)
    bad_root[bad_root.index("--data-root") + 1] = str(w.base / "elsewhere")
    with pytest.raises(SystemExit, match="REFUSED"):
        runner.main(bad_root)
    assert wit.events == []


def test_runner_end_to_end_with_test_only_gate_stub(tmp_path, monkeypatch, gate_open, capsys):
    import run_nonsealed_diagnostic as runner
    w = synth.World(tmp_path / "w")
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(w.protocol))
    argv = runner_argv(w, build_auth(w), tmp_path, protocol_path)
    assert runner.main(argv) == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["classification"] == h.CLASSIFICATION and summary["tripwire_zero_access"] is True
    receipt = json.loads((w.base / "out" / "run" / "harness_receipt.json").read_text())
    assert receipt["real_execution"] is True and receipt["authorization"]["files"]
    assert receipt["read_accounting"]["total_physical_bytes_read"] == sum(
        f["max_physical_bytes"] for f in receipt["authorization"]["files"])
