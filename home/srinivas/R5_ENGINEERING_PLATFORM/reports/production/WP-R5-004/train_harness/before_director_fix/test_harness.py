"""UNIT VERIFICATION on SYNTHETIC fixtures only. None of this is an actual replay and none reads market data."""
from __future__ import annotations

import builtins
import copy
import hashlib
import importlib
import json
import os
import shutil
import socket
import sys
from datetime import date, timedelta
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
worker = importlib.import_module("scripts.run_r5_step5_candidate")


# ------------------------------------------------------------------ helpers
def cfg_for(w, **kw):
    base = dict(snapshot_dir=SNAPSHOT, allowed_manifest_roots=(w.root,), allowed_data_roots=(w.data,),
                allowed_grid_roots=(w.grid,), output_root=w.base / "out", chunk_size=4096)
    base.update(kw)
    return h.HarnessConfig(**base)


def prepare_with(w, **kw):
    ledger = h.ReadLedger()
    prepare = h.make_prepare(cfg_for(w, **kw), ledger)
    return prepare, ledger


def run_prepare(w, **kw):
    prepare, ledger = prepare_with(w, **kw)
    return prepare(w.root, w.protocol, w.block), ledger


def world(tmp_path, name="w", **opt):
    return synth.World(tmp_path / name, **opt)


class OpenSpy:
    """Independent physical-read witness at the open() boundary (not the harness's own counters)."""

    def __init__(self, monkeypatch, roots):
        self.roots = [Path(r).resolve() for r in roots]
        self.reads = {}
        self.opened = []
        spy, real = self, builtins.open

        class Wrap:
            def __init__(self, handle, key):
                self.handle, self.key = handle, key

            def read(self, n=-1):
                data = self.handle.read(n)
                spy.reads[self.key] = spy.reads.get(self.key, 0) + len(data)
                return data

            def close(self):
                self.handle.close()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        def opener(file, mode="r", *a, **k):
            if isinstance(file, (str, os.PathLike)):
                resolved = Path(file).resolve()
                if any(resolved.is_relative_to(r) for r in spy.roots):
                    spy.opened.append(str(resolved))
                    if "b" in mode and "r" in mode:
                        return Wrap(real(file, mode, *a, **k), str(resolved))
            return real(file, mode, *a, **k)
        monkeypatch.setattr(builtins, "open", opener)


# =========================================================== 1. code identity
def test_snapshot_identity_head_hash_protected_indicator():
    info = h.verify_snapshot(SNAPSHOT)
    manifest = json.loads((PLATFORM / "SNAPSHOT_MANIFEST.json").read_text())
    assert info["head"] == h.EXPECTED_HEAD == manifest["head"]
    assert info["file_count"] == len(manifest["files"]) == 562
    assert info["files"]["revision2_external/indicators_talib.py"] == h.PROTECTED_INDICATOR[1]
    assert hashlib.sha256((SNAPSHOT / "revision2_external/indicators_talib.py").read_bytes()).hexdigest() == h.PROTECTED_INDICATOR[1]
    assert not [k for k in info["files"] if k.endswith((".csv", ".parquet"))]


def test_imported_sources_are_snapshot_only_and_listed():
    from scripts.diagnostics import r5_block1_acceptance  # noqa: F401
    importlib.import_module("revision2_external.orchestrator")
    info = h.verify_snapshot(SNAPSHOT)
    audit = h.audit_loaded_modules(SNAPSHOT, info["files"])
    assert audit["count"] > 40
    for name in ("scripts", "revision2", "revision5", "revision2_external"):
        for p in list(getattr(sys.modules[name], "__path__")):
            assert Path(p).resolve().is_relative_to(SNAPSHOT.resolve())


def test_foreign_import_from_original_repo_is_rejected(monkeypatch):
    import types
    fake = types.ModuleType("fake_original")
    fake.__file__ = "/home/srinivas/projects/zerodha-r5-governor-refactor/fake_original.py"
    monkeypatch.setitem(sys.modules, "fake_original", fake)
    with pytest.raises(h.CodeDriftError):
        h.audit_loaded_modules(SNAPSHOT, h.verify_snapshot(SNAPSHOT)["files"])


@pytest.fixture
def snapshot_copy(tmp_path):
    dst = tmp_path / "copy"
    dst.mkdir()
    shutil.copytree(SNAPSHOT, dst / "snapshot")
    shutil.copy(PLATFORM / "SNAPSHOT_MANIFEST.json", dst / "SNAPSHOT_MANIFEST.json")
    for base, dirs, names in os.walk(dst):          # the immutable snapshot is read-only; the COPY must be writable
        for n in dirs + names:
            os.chmod(Path(base) / n, 0o755 if (Path(base) / n).is_dir() else 0o644)
    return dst


def test_code_drift_modified_extra_missing_head_pin_malformed(snapshot_copy):
    snap, man = snapshot_copy / "snapshot", snapshot_copy / "SNAPSHOT_MANIFEST.json"
    assert h.verify_snapshot(snap, man)["file_count"] == 562
    with pytest.raises(h.CodeDriftError, match="pin"):
        h.verify_snapshot(snap, man, expected_manifest_sha256="0" * 64)
    with pytest.raises(h.CodeDriftError, match="malformed"):
        h.verify_snapshot(snap, man, expected_manifest_sha256="xyz")
    target = snap / "position_manager.py"
    original = target.read_bytes()
    target.write_bytes(original + b"\n# drift\n")
    with pytest.raises(h.CodeDriftError, match="mismatched"):
        h.verify_snapshot(snap, man)
    target.write_bytes(original)
    (snap / "extra_dirty.py").write_text("x=1\n")
    with pytest.raises(h.CodeDriftError, match="extra"):
        h.verify_snapshot(snap, man)
    (snap / "extra_dirty.py").unlink()
    target.unlink()
    with pytest.raises(h.CodeDriftError, match="missing"):
        h.verify_snapshot(snap, man)
    target.write_bytes(original)
    data = json.loads(man.read_text())
    data["head"] = "0" * 40
    man.write_text(json.dumps(data))
    with pytest.raises(h.CodeDriftError, match="HEAD"):
        h.verify_snapshot(snap, man)
    data["head"] = h.EXPECTED_HEAD
    data["files"]["position_manager.py"] = "nothex"
    man.write_text(json.dumps(data))
    with pytest.raises(h.CodeDriftError, match="malformed"):
        h.verify_snapshot(snap, man)


def test_protected_indicator_tamper_rejected(snapshot_copy):
    snap, man = snapshot_copy / "snapshot", snapshot_copy / "SNAPSHOT_MANIFEST.json"
    indicator = snap / h.PROTECTED_INDICATOR[0]
    indicator.write_bytes(indicator.read_bytes() + b"#")
    data = json.loads(man.read_text())
    data["files"][h.PROTECTED_INDICATOR[0]] = hashlib.sha256(indicator.read_bytes()).hexdigest()  # forged manifest too
    man.write_text(json.dumps(data))
    with pytest.raises(h.CodeDriftError, match="protected indicator"):
        h.verify_snapshot(snap, man)


def test_factory_contract_fails_closed_without_explicit_prepare():
    import types
    ok = importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
    h.assert_factory_contract(ok)
    bad = types.SimpleNamespace(execute_block=lambda root, protocol, block, params, *, output_path=None: None)
    with pytest.raises(h.HarnessError, match="refusing to bypass"):
        h.assert_factory_contract(bad)


# ================================================ 2. frame-for-frame equivalence
@pytest.mark.parametrize("opt", [
    {}, {"bom": True, "newline": "\r\n"}, {"header": "date,open,high,low,close,volume"},
], ids=["lf", "bom_crlf", "date_column"])
def test_frames_equal_original_prepare_block(tmp_path, opt):
    w = world(tmp_path, **opt)
    (frames, feeds, audit), ledger = run_prepare(w)
    ofr, ofe, oaud = worker.prepare_block(w.root, w.protocol, w.block)
    assert sorted(frames) == sorted(ofr) == list(w.symbols) and sorted(feeds) == sorted(ofe)
    for sym in frames:
        pd.testing.assert_frame_equal(frames[sym], ofr[sym], check_exact=True)
    for name in feeds:
        pd.testing.assert_frame_equal(feeds[name], ofe[name], check_exact=True)
    assert audit["clock_events"] == oaud["clock_events"] and audit["max_target_utc"] == oaud["max_target_utc"]
    for sym in w.symbols:   # original count/timestamp audit fields identical
        for k, v in oaud["stock"][sym].items():
            assert audit["stock"][sym][k] == v
    for name in feeds:
        for k in ("rows", "first_available_utc", "last_available_utc", "cutoff_utc", "rows_after_cutoff_retained"):
            assert audit["grid"][name][k] == oaud["grid"][name][k]
        assert "sha256" not in audit["grid"][name]          # no whole-file hash is produced
        assert audit["grid"][name]["boundary_rows_parsed_and_discarded"] == 1
    assert len(ledger.files) == 2 * len(w.symbols)


# ===================================================== 3. read-boundary accounting
def test_positive_read_boundary_matches_independent_spy(tmp_path, monkeypatch):
    chunk = 512
    w = world(tmp_path, mutate_rows=lambda sym, rows: rows[:-80] + [("POISON", "x", "x", "x", "x", "x")] * 80)
    spy = OpenSpy(monkeypatch, [w.data, w.grid])
    (_, _, audit), ledger = run_prepare(w, chunk_size=chunk)
    for row in ledger.files:
        sym_path = row["path"]
        assert spy.reads[sym_path] == row["physical_bytes_read"]            # accounting == independent witness
        assert 0 <= row["overread_bytes"] < chunk and row["physical_bytes_read"] < row["size_bytes"]
        assert not row["reached_eof"]
    for sym in w.symbols:
        off = w.offsets(sym)
        row = next(r for r in ledger.files if r["path"] == str(w.csv_path(sym)))
        assert row["consumed_bytes"] == off["sentinel_end"]                    # exact end of sentinel row
        data = w.csv_path(sym).read_bytes()
        assert row["consumed_prefix_sha256"] == hashlib.sha256(data[:off["sentinel_end"]]).hexdigest()
        assert row["physical_bytes_read"] <= off["sentinel_end"] + chunk - 1
        assert row["physical_bytes_read"] < data.index(b"POISON")             # poison tail never physically read
    summary = ledger.summary()
    assert summary["total_physical_bytes_read"] < summary["total_file_size_bytes_metadata"]
    assert summary["full_file_hash_calls"] == 0


def test_poison_beyond_boundary_does_not_change_anything(tmp_path):
    def poison(sym, blob):
        cut = synth.World(tmp_path / f"probe_{sym}").offsets(sym)["sentinel_end"] + 3000
        return blob[:cut] + b"\xff\xfePOISON-NOT-CSV\x00\n" * 50
    clean = world(tmp_path, "clean")
    dirty = world(tmp_path, "dirty", mutate_blob=poison)
    (fa, ga, aa), la = run_prepare(clean, chunk_size=512)
    (fb, gb, ab), lb = run_prepare(dirty, chunk_size=512)
    assert aa["slice_sha256"] == ab["slice_sha256"]
    assert [r["consumed_prefix_sha256"] for r in la.files] == [r["consumed_prefix_sha256"] for r in lb.files]
    for sym in fa:
        pd.testing.assert_frame_equal(fa[sym], fb[sym])


def test_negative_control_whole_file_read_is_detected(tmp_path):
    w = world(tmp_path)
    prepare, _ = prepare_with(w, chunk_size=1 << 20)       # chunk > file: unbounded read would swallow the file
    with pytest.raises(h.ReadBoundaryError, match="bounded access not proven"):
        prepare(w.root, w.protocol, w.block)
    (_, _, audit), ledger = run_prepare(w, chunk_size=1 << 20, strict_prefix=False)   # explicit opt-out only
    assert all(r["physical_bytes_read"] == r["size_bytes"] for r in ledger.files)   # the whole file was swallowed
    cap_prepare, _ = prepare_with(w, chunk_size=512, max_physical_bytes_per_file=1000)
    with pytest.raises(h.ReadBoundaryError, match="physical read cap"):
        cap_prepare(w.root, w.protocol, w.block)


def test_reader_line_cap_and_record_invariants(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(b"a\n" + b"z" * (h.MAX_LINE_BYTES + 10) + b"\n")
    r = h.BoundedLineReader(p, chunk_size=1 << 18)
    assert r.next_line() == b"a\n"
    with pytest.raises(h.ReadBoundaryError, match="exceeds"):
        r.next_line()
    r.close()
    with pytest.raises(h.HarnessError):
        h.BoundedLineReader(p, chunk_size=0)


# ============================================== 4. full-hash spy / content change
def test_hash_spy_no_whole_file_hash_only_consumed_bytes(tmp_path, monkeypatch):
    w = world(tmp_path)
    lens, others, calls = [], [], []
    real = hashlib.sha256

    def note(n):
        code = sys._getframe(2).f_code
        (lens if code.co_name == "_consume" and code.co_filename.endswith("wp004_train_harness.py") else others).append((n, code.co_filename))

    class SpyHash:
        def __init__(self, data=b""):
            self._h = real()
            if data:
                note(len(data))
                self._h.update(data)

        def update(self, data):
            note(len(data))
            self._h.update(data)

        def hexdigest(self):
            return self._h.hexdigest()

    monkeypatch.setattr(hashlib, "sha256", SpyHash)
    banned = lambda *a, **k: calls.append(a)  # noqa: E731
    monkeypatch.setattr(worker, "sha256_file", banned)
    ds = importlib.import_module("revision2.dataset_manifest")
    monkeypatch.setattr(ds, "_sha256_file", banned)
    monkeypatch.setattr(ds, "verify_manifest", banned)
    monkeypatch.setattr(h, "sha256_code_file", banned)
    (_, _, audit), ledger = run_prepare(w)
    assert not calls
    total_consumed = ledger.summary()["total_consumed_bytes"]
    assert sum(n for n, _ in lens) == total_consumed       # bytes hashed by the line reader == exactly the consumed bytes
    sizes = [r["size_bytes"] for r in ledger.files]
    assert max(n for n, _ in lens) < min(sizes)
    assert all(n < min(sizes) / 4 for n, _ in others), others   # others: manifest-record JSON + slice JSON only
    assert not [c for _, c in others if "csv" in c.lower()]
    assert all(r["consumed_bytes"] < r["size_bytes"] for r in ledger.files)


def test_actual_content_change_detected_where_counts_would_not(tmp_path):
    def flip(sym, blob):
        lines = blob.split(b"\n")
        if sym != "AAA":
            return blob
        i = 140                          # a target-session row of the same length: change one volume digit
        head, last = lines[i].rsplit(b",", 1)
        lines[i] = head + b"," + last[:-1] + (b"7" if last[-1:] != b"7" else b"3")
        return b"\n".join(lines)
    a = world(tmp_path, "a")
    b = world(tmp_path, "b", mutate_blob=flip)
    assert a.csv_path("AAA").stat().st_size == b.csv_path("AAA").stat().st_size
    (_, _, aa), la = run_prepare(a)
    (_, _, ab), lb = run_prepare(b)
    strip = lambda aud: {s: {k: v for k, v in r.items() if k not in ("consumed_prefix_sha256", "consumed_bytes", "physical_bytes_read")}  # noqa: E731
                         for s, r in aud["stock"].items()}
    assert strip(aa) == strip(ab)                                   # counts/timestamps-only audit: identical (insufficient)
    assert aa["stock"]["AAA"]["consumed_prefix_sha256"] != ab["stock"]["AAA"]["consumed_prefix_sha256"]
    assert aa["stock"]["BBB"]["consumed_prefix_sha256"] == ab["stock"]["BBB"]["consumed_prefix_sha256"]
    assert aa["slice_sha256"] != ab["slice_sha256"]                 # block identity binds consumed content


def test_provenance_limit_same_size_edit_passes_metadata_but_changes_recorded_hash(tmp_path):
    """Documented limit: manifest sha/size cannot prove prefix integrity; the consumed-prefix hash is the only evidence."""
    w = world(tmp_path)
    path = w.csv_path("AAA")
    data = path.read_bytes()
    lines = data.split(b"\n")
    head, last = lines[140].rsplit(b",", 1)
    lines[140] = head + b"," + (b"1" if last[-1:] != b"1" else b"2") * len(last)
    path.write_bytes(b"\n".join(lines))
    assert path.stat().st_size == len(data)
    (_, _, edited), _ = run_prepare(w)                       # passes: whole-file manifest sha is deliberately not re-hashed
    assert hashlib.sha256(path.read_bytes()).hexdigest() != json.loads((w.root / "revision2/MANIFEST.json").read_text())["files"][0]["sha256"]
    (_, _, clean), _ = run_prepare(world(tmp_path, "clean2"))
    assert edited["stock"]["AAA"]["consumed_prefix_sha256"] != clean["stock"]["AAA"]["consumed_prefix_sha256"]


# ======================================================== 5. chronology / sentinel
def test_missing_sentinel(tmp_path):
    w = world(tmp_path, mutate_rows=lambda s, rows: rows[:-3 * 40])
    with pytest.raises(ValueError, match="boundary sentinel missing"):
        run_prepare(w)


def test_out_of_order_sentinel(tmp_path):
    def mut(sym, rows):
        i = len(rows) - 3 * 40
        rows[i] = (synth.stamp(date.fromisoformat(w_dates[0]), 5),) + tuple(rows[i][1:])
        return rows
    w_dates = ["2023-12-04"]
    w = world(tmp_path, mutate_rows=mut)
    with pytest.raises(h.ChronologyError, match="not strictly increasing"):
        run_prepare(w)


def test_duplicate_and_swapped_timestamps(tmp_path):
    def dup(sym, rows):
        rows[130] = rows[129]
        return rows

    def swap(sym, rows):
        rows[130], rows[131] = rows[131], rows[130]
        return rows
    for fn in (dup, swap):
        with pytest.raises(h.ChronologyError):
            run_prepare(world(tmp_path, f"w_{fn.__name__}", mutate_rows=fn))


def test_unexpected_missing_first_and_short_warmup(tmp_path):
    w = world(tmp_path, "unexpected")
    skipped = [w.sessions[0], "2023-12-07"]   # file also has 12-05 and 12-06                    # skips file's second target day -> unexpected real session
    w.block["sessions"] = skipped
    w.protocol["sampling_plan"]["stage_b"][0]["sessions"] = skipped
    with pytest.raises(ValueError, match="unexpected real session"):
        prepare_with(w)[0](w.root, w.protocol, w.block)
    w = world(tmp_path, "missing_session",
              mutate_rows=lambda s, rows: [r for r in rows if not r[0].startswith("2023-12-05")])
    with pytest.raises(ValueError, match="missing target sessions"):
        prepare_with(w)[0](w.root, w.protocol, w.block)
    w = world(tmp_path, "first_missing")
    sess = ["2023-12-02", *w.sessions]                          # a Saturday that has no rows
    w.block["sessions"] = sess
    w.protocol["sampling_plan"]["stage_b"][0]["sessions"] = sess
    with pytest.raises(ValueError, match="first target session missing"):
        prepare_with(w)[0](w.root, w.protocol, w.block)
    w = world(tmp_path, "short_warmup", bars=40)
    w.protocol["block_execution_contract"]["stock_warmup_bars_per_symbol"] = 130
    with pytest.raises(ValueError, match="expected 130 warmup bars"):
        prepare_with(w)[0](w.root, w.protocol, w.block)


def test_train_boundary_and_block_validation_before_any_read(tmp_path, monkeypatch):
    w = world(tmp_path, train_end="2023-12-05")                # block spans past TRAIN end
    spy = OpenSpy(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.ChronologyError, match="outside TRAIN"):
        run_prepare(w)
    assert spy.opened == []                                    # rejected before touching market data
    w = world(tmp_path, "sentinel_at_end", train_end="2023-12-06")   # last target 12-05, sentinel day == TRAIN end
    with pytest.raises(h.ChronologyError, match="at/after TRAIN end"):
        run_prepare(w)
    w = world(tmp_path, "bad_block")
    w.block["block"] = 2
    with pytest.raises(h.HarnessError, match="Block 1 only"):
        run_prepare(w)
    w = world(tmp_path, "other_sessions")
    w.protocol["sampling_plan"]["stage_b"][0]["sessions"] = ["2023-12-05", "2023-12-06"]
    with pytest.raises(h.HarnessError, match="Stage B Block 1"):
        run_prepare(w)
    w = world(tmp_path, "live", live_trading=True)
    with pytest.raises(h.HarnessError, match="live_trading"):
        run_prepare(w)
    w = world(tmp_path, "unordered")
    w.block["sessions"] = list(reversed(w.sessions))
    w.protocol["sampling_plan"]["stage_b"][0]["sessions"] = list(reversed(w.sessions))
    with pytest.raises(h.ChronologyError, match="ascending"):
        run_prepare(w)


def test_shape_errors(tmp_path):
    cases = {
        "short_row": lambda s, b: _line_edit(b, 100, lambda l: l.rsplit(b",", 1)[0]),
        "extra_field": lambda s, b: _line_edit(b, 100, lambda l: l + b",9"),
        "quoted": lambda s, b: _line_edit(b, 100, lambda l: b'"' + l.split(b",", 1)[0] + b'",' + l.split(b",", 1)[1]),
        "lone_cr": lambda s, b: _line_edit(b, 100, lambda l: l.replace(b",", b"\r", 1)),
        "dup_header": lambda s, b: b.replace(b"timestamp,open,high", b"timestamp,open,open", 1),
        "missing_col": lambda s, b: b.replace(b",volume\n", b",vol\n", 1),
    }
    for name, mut in cases.items():
        w = world(tmp_path, name, mutate_blob=mut)
        with pytest.raises(h.HarnessError):
            run_prepare(w)
    w = world(tmp_path, "empty", mutate_blob=lambda s, b: b"")
    with pytest.raises((h.HarnessError, KeyError, ValueError)):
        run_prepare(w)


def _line_edit(blob, index, fn):
    lines = blob.split(b"\n")
    lines[index] = fn(lines[index])
    return b"\n".join(lines)


# =============================================== 6. grid causal prefix handling
def test_grid_unsorted_nonboundary_and_poison_tail(tmp_path):
    def swap(name, rows):
        rows[3], rows[4] = rows[4], rows[3]
        return rows
    with pytest.raises(h.ChronologyError):
        run_prepare(world(tmp_path, "unsorted", mutate_grid=swap))

    def truncate(name, rows):
        return [r for r in rows if r[0][:10] < "2023-12-05"]
    with pytest.raises(h.ReadBoundaryError):
        run_prepare(world(tmp_path, "no_boundary", mutate_grid=truncate))

    def poison_tail(name, rows):
        return [r if r[0][:10] <= "2023-12-06" else ("POISON", "x") for r in rows]
    (_, feeds, audit), ledger = run_prepare(world(tmp_path, "poison_grid", mutate_grid=poison_tail), chunk_size=256)
    for f in feeds.values():
        assert f["timestamp"].max() <= pd.Timestamp(audit["max_target_utc"])
    for name in feeds:
        assert audit["grid"][name]["rows_after_cutoff_retained"] == 0
        assert audit["grid"][name]["boundary_rows_parsed_and_discarded"] == 1


def test_grid_consumed_hash_changes_with_content_inside_prefix(tmp_path):
    def tweak(name, rows):
        rows[10] = (rows[10][0], round(rows[10][1] + 0.01, 2))
        return rows
    (_, _, a), _ = run_prepare(world(tmp_path, "g1"))
    (_, _, b), _ = run_prepare(world(tmp_path, "g2", mutate_grid=tweak))
    assert a["grid"]["NIFTY_50_15MIN"]["consumed_prefix_sha256"] != b["grid"]["NIFTY_50_15MIN"]["consumed_prefix_sha256"]
    assert a["slice_sha256"] != b["slice_sha256"]


# ================================================= 7. manifest / root rejection
def test_wrong_manifest_variants(tmp_path):
    with pytest.raises(ValueError, match="identity mismatch"):
        run_prepare(world(tmp_path, "pin", protocol_hash=synth.sha(b"other")))
    with pytest.raises(h.ManifestMismatchError, match="malformed"):
        run_prepare(world(tmp_path, "mal", protocol_hash="zz"))
    forged = synth.sha(b"forged")
    with pytest.raises(h.ManifestMismatchError, match="reproduce"):
        run_prepare(world(tmp_path, "stored", protocol_hash=forged, stored_manifest_hash=forged))
    with pytest.raises(h.ManifestMismatchError, match="first row"):
        run_prepare(world(tmp_path, "first_ts", first_ts="2023-07-03T09:15:00+05:30"))
    w = world(tmp_path, "size")
    with w.csv_path("AAA").open("ab") as fh:
        fh.write(b"\n")
    with pytest.raises(h.ManifestMismatchError, match="size"):
        run_prepare(w)
    w = world(tmp_path, "tamper")
    path = w.root / "revision2" / "MANIFEST.json"
    data = json.loads(path.read_text())
    data["files"][0]["size_bytes"] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(h.ManifestMismatchError, match="reproduce"):
        run_prepare(w)
    w = world(tmp_path, "count")
    w.protocol["stock_dataset"]["symbols"] = 48
    with pytest.raises(h.ManifestMismatchError, match="symbol count"):
        run_prepare(w)
    w = world(tmp_path, "symcount")
    path = w.root / "revision2" / "MANIFEST.json"
    data = json.loads(path.read_text())
    data["symbol_count"] = 7
    path.write_text(json.dumps(data))
    with pytest.raises(h.ManifestMismatchError, match="inconsistent"):
        run_prepare(w)


def test_unsafe_roots_and_paths(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    w = world(tmp_path, "datadir", data_dir=other)
    with pytest.raises(h.UnsafeRootError, match="data_dir"):
        run_prepare(w)
    w = world(tmp_path, "root")
    with pytest.raises(h.UnsafeRootError):
        prepare_with(w, allowed_manifest_roots=(other,))[0](w.root, w.protocol, w.block)
    with pytest.raises(h.UnsafeRootError):
        prepare_with(w)[0](Path("relative/root"), w.protocol, w.block)
    with pytest.raises(h.UnsafeRootError):
        prepare_with(w, allowed_manifest_roots=(Path("rel"),))
    w.protocol["stock_dataset"]["manifest"] = "../escape.json"
    with pytest.raises(h.UnsafeRootError, match="root-relative"):
        run_prepare(w)
    w = world(tmp_path, "gridpath")
    stray = other / "NIFTY_50_15MIN.csv"
    shutil.copy(w.grid / "NIFTY_50_15MIN.csv", stray)
    entries = json.loads((w.root / "local_workspace/records/grid.json").read_text())
    entries["files"][0]["path"] = str(stray)
    entries["files"][1]["path"] = str(stray)
    (w.root / "local_workspace/records/grid.json").write_text(json.dumps(entries))
    with pytest.raises((h.UnsafeRootError, ValueError)):
        run_prepare(w)
    w = world(tmp_path, "symlink")
    real = other / "AAA.csv"
    shutil.move(str(w.csv_path("AAA")), real)
    w.csv_path("AAA").symlink_to(real)
    with pytest.raises(h.UnsafeRootError):
        run_prepare(w)
    w = world(tmp_path, "badname")
    path = w.root / "revision2" / "MANIFEST.json"
    data = json.loads(path.read_text())
    data["files"][0]["filename"] = "../AAA.csv"
    data["files"][0]["sha256"] = data["files"][0]["sha256"]
    path.write_text(json.dumps(data))
    with pytest.raises((h.UnsafeRootError, h.ManifestMismatchError)):
        run_prepare(w)


def test_grid_manifest_metadata_rejections(tmp_path):
    w = world(tmp_path, "gsha")
    p = w.root / "local_workspace/records/grid.json"
    d = json.loads(p.read_text())
    d["files"][0]["sha256"] = "0" * 64
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="SHA mismatch"):
        run_prepare(w)
    d["files"][0]["sha256"] = "bad"
    p.write_text(json.dumps(d))
    with pytest.raises(h.ManifestMismatchError, match="malformed"):
        run_prepare(w)
    w = world(tmp_path, "gset")
    p = w.root / "local_workspace/records/grid.json"
    d = json.loads(p.read_text())
    d["files"] = d["files"][:1]
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="feed set"):
        run_prepare(w)
    w = world(tmp_path, "gdup")
    p = w.root / "local_workspace/records/grid.json"
    d = json.loads(p.read_text())
    d["files"].append(d["files"][0])
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="feed set"):
        run_prepare(w)


# ====================================================== 8. output guard / tripwire
def test_output_guard(tmp_path):
    w = world(tmp_path)
    cfg = cfg_for(w)
    ok = h.check_output_path(w.base / "out" / "run", cfg)
    assert ok == (w.base / "out" / "run").resolve()
    for bad in (w.base / "elsewhere", w.base / "out", SNAPSHOT / "x", w.data / "x", w.base / "out" / ".." / "x",
                Path("relative"), Path("/home/srinivas/projects/zerodha-phase1/out")):
        with pytest.raises(h.UnsafeRootError):
            h.check_output_path(bad, cfg)
    (w.base / "out" / "used").mkdir(parents=True)
    (w.base / "out" / "used" / "f").write_text("x")
    with pytest.raises(h.UnsafeRootError, match="pre-exist"):
        h.check_output_path(w.base / "out" / "used", cfg)
    inside_repo = cfg_for(w, output_root=Path("/home/srinivas/projects/zerodha-r5-governor-refactor/out"))
    with pytest.raises(h.UnsafeRootError):
        h.check_output_path("/home/srinivas/projects/zerodha-r5-governor-refactor/out/x", inside_repo)


@pytest.mark.parametrize("module,dotted", h.TRIPWIRE_TARGETS)
def test_tripwire_negative_control_each_target_fires(tmp_path, module, dotted):
    importlib.import_module(module)
    originals = {}
    mod = importlib.import_module(module)
    owner = mod if "." not in dotted else getattr(mod, dotted.split(".")[0])
    originals[dotted] = owner.__dict__[dotted.split(".")[-1]] if isinstance(owner, type) else getattr(owner, dotted.split(".")[-1])
    with h.Tripwire() as tw:
        obj = mod
        for part in dotted.split("."):
            obj = getattr(obj, part)
        with pytest.raises(h.TripwireViolation):
            obj()
        assert tw.counts == {f"{module}:{dotted}": 1}
        assert not tw.report()["zero_access"]
    restored = owner.__dict__[dotted.split(".")[-1]] if isinstance(owner, type) else getattr(owner, dotted.split(".")[-1])
    assert restored is originals[dotted]


def test_tripwire_network_open_and_write_controls(tmp_path):
    w = world(tmp_path)
    real_open, real_conn = builtins.open, socket.create_connection
    with h.Tripwire(forbidden_read_roots=[w.data, w.grid], allowed_write_roots=[w.base / "out"]) as tw:
        with pytest.raises(h.TripwireViolation):
            socket.create_connection(("127.0.0.1", 9))
        with pytest.raises(h.TripwireViolation):
            socket.getaddrinfo("example.invalid", 80)
        with pytest.raises(h.TripwireViolation):
            socket.socket().connect(("127.0.0.1", 9))
        with pytest.raises(h.TripwireViolation):
            open(w.csv_path("AAA"), "rb")
        with pytest.raises(h.TripwireViolation):
            w.csv_path("AAA").read_bytes()
        with pytest.raises(h.TripwireViolation):
            pd.read_csv(w.csv_path("AAA"))
        stray = w.base / "stray.txt"
        with pytest.raises(h.TripwireViolation):
            open(stray, "w")
        assert not stray.exists()
        (w.base / "out").mkdir(exist_ok=True)
        with open(w.base / "out" / "fine.txt", "w") as fh:         # permitted write inside the output root
            fh.write("ok")
        assert len(tw.violations) == 7
    assert builtins.open is real_open and socket.create_connection is real_conn


def test_harness_reader_allowed_under_tripwire_while_raw_open_is_not(tmp_path):
    w = world(tmp_path)
    prepare, ledger = prepare_with(w)
    with h.Tripwire(forbidden_read_roots=[w.data, w.grid], allowed_write_roots=[w.base / "out"]) as tw:
        prepare(w.root, w.protocol, w.block)
        assert tw.report()["zero_access"] and ledger.files


# ============================================================ 9. end-to-end (synthetic)
@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    w = synth.World(base)
    cfg = cfg_for(w)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in list(w.data.iterdir()) + list(w.grid.iterdir())}
    pre = h.verify_snapshot(SNAPSHOT)
    result, receipt = h.run_block_diagnostic(cfg, w.root, w.protocol, w.block, {}, w.base / "out" / "run1",
                                             expected_manifest_sha256=pre["manifest_sha256"])
    orig = worker.execute_block(w.root, w.protocol, w.block, {})
    return dict(w=w, result=result, receipt=receipt, orig=orig, before=before, pre=pre)


def test_e2e_direct_factory_route_and_receipt(e2e):
    r, rc = e2e["result"], e2e["receipt"]
    assert rc["classification"] == "NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC"
    assert rc["route"]["combined_cycle_state_path"] is None and rc["route"]["fleet_loading_policy"] is None
    assert rc["route"]["feedback_compaction"] is False and rc["combined_cycle_runtime"] is None
    assert "combined_cycle_runtime" not in r
    out = Path(e2e["w"].base / "out" / "run1")
    assert json.loads((out / "runtime_receipts.json").read_text()) is None
    assert (out / "harness_receipt.json").is_file() and (out / "acceptance_result.json").is_file()
    assert rc["snapshot"]["tree_sha256"] == e2e["pre"]["tree_sha256"]
    assert rc["imported_sources"]["count"] > 40
    assert r["audit"]["loader"] == h.LOADER_ID and rc["read_accounting"]["full_file_hash_calls"] == 0


def test_e2e_zero_cnc_gtt_tick_conversion_access(e2e):
    t = e2e["receipt"]["tripwire"]
    assert t["zero_access"] and t["counts"] == {} and t["violations"] == []
    assert len(t["targets"]) == len(h.TRIPWIRE_TARGETS)
    assert "kiteconnect:KiteConnect.__init__" in t["targets"][0]   # the kiteconnect module is loaded (import-only); its client is tripwired


def test_e2e_matches_original_worker_engine_outputs_on_synthetic_block(e2e):
    r, o = e2e["result"], e2e["orig"]
    for key in ("metrics", "plant_control", "governor_authority", "micom", "trades"):
        assert r[key] == o[key], key
    assert r["audit"]["slice_sha256"] != o["audit"]["slice_sha256"]      # content-bound identity differs by design


def test_e2e_inputs_and_snapshot_unmodified_and_reads_bounded(e2e):
    w = e2e["w"]
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in list(w.data.iterdir()) + list(w.grid.iterdir())}
    assert after == e2e["before"]
    assert h.verify_snapshot(SNAPSHOT)["tree_sha256"] == e2e["pre"]["tree_sha256"]
    acc = e2e["receipt"]["read_accounting"]
    assert acc["total_physical_bytes_read"] < acc["total_file_size_bytes_metadata"]
    written = {p.relative_to(w.base / "out").as_posix() for p in (w.base / "out").rglob("*") if p.is_file()}
    assert "run1/harness_receipt.json" in written and not any(x.startswith("..") for x in written)


def test_e2e_snapshot_drift_blocks_before_any_market_read(tmp_path, monkeypatch, snapshot_copy):
    w = world(tmp_path)
    snap = snapshot_copy / "snapshot"
    (snap / "position_manager.py").write_bytes((snap / "position_manager.py").read_bytes() + b"#x\n")
    spy = OpenSpy(monkeypatch, [w.data, w.grid])
    cfg = cfg_for(w, snapshot_dir=snap)
    with pytest.raises(h.CodeDriftError, match="mismatched"):
        h.run_block_diagnostic(cfg, w.root, w.protocol, w.block, {}, w.base / "out" / "r")
    assert spy.opened == [] and not (w.base / "out" / "r").exists()


def test_e2e_rejects_bad_output_before_any_market_read(tmp_path, monkeypatch):
    w = world(tmp_path)
    spy = OpenSpy(monkeypatch, [w.data, w.grid])
    with pytest.raises(h.UnsafeRootError):
        h.run_block_diagnostic(cfg_for(w), w.root, w.protocol, w.block, {}, tmp_path / "outside")
    assert spy.opened == []


def test_e2e_governor_path_exercised_equals_original_worker(tmp_path):
    """Labels only (INFY/TCS/HDFCBANK) so the governor maps symbols; every price/volume/grid value is synthetic."""
    w = world(tmp_path, symbols=("INFY", "TCS", "HDFCBANK"), bars=120)
    result, receipt = h.run_block_diagnostic(cfg_for(w), w.root, w.protocol, w.block, {}, w.base / "out" / "run")
    original = worker.execute_block(w.root, w.protocol, w.block, {})
    assert result["governor_authority"]["entry_decisions"].get("ENTRY:GOVERNOR_ENTRY", 0) > 0   # decision path exercised
    for key in ("metrics", "plant_control", "governor_authority", "micom", "trades"):
        assert result[key] == original[key], key
    assert receipt["tripwire"]["zero_access"] and receipt["tripwire"]["counts"] == {}
    assert result["native_accounting_reconciliation"]["passed"]


# ================================================================ 10. audited runner
def test_runner_refuses_without_valid_authorization(tmp_path, monkeypatch):
    import run_nonsealed_diagnostic as runner
    w = world(tmp_path)
    spy = OpenSpy(monkeypatch, [w.data, w.grid])
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"execution_package_id": "X", "authorizes_real_data_read": False}))
    pin = "0" * 64
    argv = ["--authorization", str(auth), "--snapshot-manifest-sha256", pin, "--protocol-sha256", pin,
            "--params-json", str(auth), "--params-sha256", pin, "--root", str(w.root), "--data-root", str(w.data),
            "--grid-root", str(w.grid), "--output-root", str(w.base / "out"), "--output-dir", str(w.base / "out" / "r")]
    with pytest.raises(SystemExit, match="REFUSED"):
        runner.main(argv)
    with pytest.raises(SystemExit):
        runner.main([])                                   # no defaults: every pin/root is mandatory
    auth.write_text(json.dumps({"execution_package_id": "X", "authorizes_real_data_read": True,
                                "classification": h.CLASSIFICATION}))
    with pytest.raises(h.HarnessError, match="pin"):
        runner.main(argv)                                 # wrong protocol pin rejected before any read
    assert spy.opened == [] and not (w.base / "out" / "r").exists()
