"""WP-R5-004-OS-ISOLATION: ACTUAL bwrap launches against SYNTHETIC generated fixtures. No market data, no replay, no broker.

Every sandbox test starts a real bwrap namespace; nothing here is a mock of the boundary. A host-side negative control
runs the same probe unsandboxed to show the probe is sensitive (canary readable, listener reachable).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

PLATFORM = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
HARNESS = Path(os.environ.get("WP004_OS_HARNESS_DIR", str(PLATFORM / "harness")))   # mutation_os_isolation.py points this at a mutated copy
PROBES = PLATFORM / "harness_tests" / "os_probes"
PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HARNESS))

import os_isolation as osi  # noqa: E402
import wp004_train_harness as h  # noqa: E402

CANARY_TEXT = "CANARY-HOST-SECRET-7f3a"
ALLOWED_TEXT = "SYNTHETIC-TRAIN-ARTIFACT-OK"
FORBIDDEN_COMPONENTS = ["R5_ENGINEERING_PLATFORM", "zerodha-r5-governor-refactor", "projects", "Documents", ".ssh", "reports",
                        "test_tmp", "host_secret", "train_input", "canary.txt", "h.sock","SIBLING_SHOULD_NOT_APPEAR.csv"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def world():
    # fixtures live OUTSIDE /tmp (the sandbox has its own /tmp tmpfs, which would mask a /tmp canary for the wrong reason)
    root = Path(tempfile.mkdtemp(prefix="o_", dir=PLATFORM / "test_tmp"))
    inputs = root / "train_input"
    secret = root / "host_secret"
    out = root / "scratch_out"
    probe_code = root / "probe_code"
    for d in (inputs, secret, out, probe_code):
        d.mkdir()
    (inputs / "stock_SYN.csv").write_text(f"ts,close\n{ALLOWED_TEXT}\n")
    (inputs / "grid_SYN.csv").write_text("ts,v\n1,2\n")
    (inputs / "SIBLING_SHOULD_NOT_APPEAR.csv").write_text("sibling\n")        # same dir as approved inputs
    (secret / "canary.txt").write_text(CANARY_TEXT)
    for f in PROBES.glob("*.py"):
        shutil.copy2(f, probe_code / f.name)
    lst = socket.socket()
    lst.bind(("127.0.0.1", 0))
    lst.listen(8)
    stop = threading.Event()

    def accept():
        lst.settimeout(0.2)
        while not stop.is_set():
            try:
                c, _ = lst.accept()
                world.hits.append(1)
                c.close()
            except (socket.timeout, OSError):
                pass

    unix_path = str(secret / "h.sock")        # AF_UNIX paths are limited to 107 bytes
    us = socket.socket(socket.AF_UNIX)
    us.bind(unix_path)
    us.listen(4)
    world.hits = []
    t = threading.Thread(target=accept, daemon=True)
    t.start()
    w = dict(root=root, inputs=inputs, secret=secret, out=out, probe_code=probe_code, port=lst.getsockname()[1],
             unix=unix_path, canary=str(secret / "canary.txt"), listener_hits=world.hits)
    yield w
    stop.set()
    lst.close()
    us.close()
    shutil.rmtree(root, ignore_errors=True)


def make_spec(world, target="probe/probe_all.py", args=(), inputs=True, out=None, **kw):
    arts = ()
    if inputs:
        arts = tuple(osi.InputArtifact(str(world["inputs"] / n), n, sha(world["inputs"] / n), "SYNTHETIC-APPROVAL-1")
                     for n in ("stock_SYN.csv", "grid_SYN.csv"))
    roots = {"harness": str(HARNESS), "probe": str(world["probe_code"])}
    pins = {k: osi.tree_sha256(v) for k, v in roots.items()}
    base = dict(python=PY, code_roots=roots, code_pins=pins, target=target, target_args=tuple(args), inputs=arts,
                output_dir=str(out or world["out"]), timeout_s=180,
                protected_paths=(str(world["secret"]), "/home/srinivas/projects/zerodha-r5-governor-refactor",
                                 "/home/srinivas/projects/zerodha-phase1"),
                no_expose_paths=("/home/srinivas/R5_ENGINEERING_PLATFORM", "/home/srinivas/R5_ENGINEERING_PLATFORM/work",
                                 str(PLATFORM), "/home/srinivas/projects"))
    base.update(kw)
    return osi.IsolationSpec(**base)


def probe_cfg(world, **extra):
    cfg = dict(allowed=["/in/stock_SYN.csv"],
               denied=[world["canary"], "/home/srinivas/projects/zerodha-r5-governor-refactor/README.md",
                       "/home/srinivas/.bashrc", "/etc/passwd"],
               tcp=["127.0.0.1", world["port"]], unix=world["unix"], forbidden_components=FORBIDDEN_COMPONENTS,
               write_ok=["/out/probe_output.txt", "/scratch/s.txt", "/tmp/t.txt"],
               write_denied=["/code/harness/NEW_FILE.py", "/code/harness/os_isolation.py", "/in/stock_SYN.csv", "/in/NEW.csv",
                             "/etc/NEW", world["canary"] + ".new"],
               runtime_prefixes=["/usr", "/lib", "/lib64", "/home/srinivas/.venvs", "/home/srinivas/.local",
                                 "/home/srinivas"])
    cfg.update(extra)
    return cfg


def run_probe(world, **extra):
    cfg = probe_cfg(world, **extra)
    res = osi.launch(make_spec(world, args=(json.dumps(cfg),)))
    return res, parse(res)


def parse(res):
    for line in res.stdout.splitlines():
        if line.startswith("PROBE_JSON:"):
            return json.loads(line[len("PROBE_JSON:"):])
    return None


@pytest.fixture(scope="module")
def sandboxed(world):
    return run_probe(world)


def test_environment_supported():
    env = osi.check_environment()
    assert env["bwrap"] == "/usr/bin/bwrap" and len(env["bwrap_sha256"]) == 64


def test_launch_ok_and_interpreter_is_the_permitted_venv(sandboxed):
    res, R = sandboxed
    assert res.ok, (res.status, res.detail, res.stderr[-800:])
    assert res.argv[res.argv.index("--") + 1] == PY
    assert R is not None


# ------------------------------------------------------------------ allowed reads
def test_allowed_fixture_reads_work_through_every_api(sandboxed):
    _, R = sandboxed
    for api in ("builtins_open", "os_open", "mmap", "ctypes_libc", "subprocess_python"):
        r = R[f"allowed:{api}:stock_SYN.csv"]
        assert r["ok"], (api, r)
    assert ALLOWED_TEXT in R["allowed:builtins_open:stock_SYN.csv"]["value"]
    assert ALLOWED_TEXT in R["allowed:os_open:stock_SYN.csv"]["value"]
    assert ALLOWED_TEXT in R["allowed:mmap:stock_SYN.csv"]["value"]
    assert ALLOWED_TEXT in R["allowed:ctypes_libc:stock_SYN.csv"]["value"]


# ------------------------------------------------------------------ denied reads
DENIED_APIS = ("builtins_open", "os_open", "mmap", "ctypes_libc", "raw_syscall", "subprocess_python", "subprocess_shell",
               "fork_child", "dotdot", "proc_self_root", "proc_1_root")


def test_outside_reads_denied_for_every_api_and_descendant(world, sandboxed):
    _, R = sandboxed
    for path in probe_cfg(world)["denied"]:
        for api in DENIED_APIS:
            r = R[f"denied:{api}:{path}"]
            if api == "subprocess_shell":
                assert not r["ok"] or r["value"] == "", (path, r)       # no /bin/cat at all, never the content
                continue
            assert not r["ok"], f"{api} read {path}: {r}"
        assert not R[f"denied:listdir:{path}"]["ok"] or CANARY_TEXT not in json.dumps(R)
    assert CANARY_TEXT not in json.dumps(R)


def test_negative_control_host_probe_reads_canary_and_reaches_listener(world):
    cfg = probe_cfg(world, allowed=[], denied=[world["canary"]], write_ok=[], write_denied=[])
    r = subprocess.run([PY, "-I", str(PROBES / "probe_all.py"), json.dumps(cfg)], capture_output=True, text=True, timeout=120)
    R = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("PROBE_JSON:")][0][11:])
    assert R[f"denied:builtins_open:{world['canary']}"]["ok"]
    assert R[f"denied:os_open:{world['canary']}"]["ok"]
    assert R[f"denied:mmap:{world['canary']}"]["ok"]
    assert R[f"denied:ctypes_libc:{world['canary']}"]["ok"]
    assert R[f"denied:subprocess_python:{world['canary']}"]["ok"]
    assert R["net:tcp_loopback_listener"]["ok"] and R["net:unix_socket"]["ok"]


# ------------------------------------------------------------------ network
def test_network_denied_including_child_processes(world, sandboxed):
    _, R = sandboxed
    before = len(world["listener_hits"])
    assert not R["net:tcp_loopback_listener"]["ok"]
    assert not R["net:subprocess_tcp"]["ok"]
    assert not R["net:unix_socket"]["ok"]
    assert R["net:ifaces"]["value"] in ([], ["lo"])
    assert len(world["listener_hits"]) == before        # the host listener never saw a connection


# ------------------------------------------------------------------ writes
def test_output_writes_allowed_and_visible_on_host(world, sandboxed):
    _, R = sandboxed
    for k in ("write_ok:builtins:/out/probe_output.txt", "write_ok:os:/out/probe_output.txt.os",
              "write_ok:builtins:/scratch/s.txt", "write_ok:builtins:/tmp/t.txt"):
        assert R[k]["ok"], (k, R[k])
    assert (world["out"] / "probe_output.txt").read_text() == "isolated output"
    assert (world["out"] / "probe_output.txt.os").exists()
    assert not (Path("/scratch") / "s.txt").exists()          # scratch is private tmpfs, nothing lands on the host


def test_source_and_input_writes_denied_and_sources_unchanged(world, sandboxed):
    _, R = sandboxed
    for p in ("/code/harness/NEW_FILE.py", "/code/harness/os_isolation.py", "/in/stock_SYN.csv", "/in/NEW.csv", "/etc/NEW"):
        for api in ("builtins", "os", "subprocess"):
            assert not R[f"write_denied:{api}:{p}"]["ok"], (api, p)
    assert not R["write_denied:root"]["ok"]
    assert not (HARNESS / "NEW_FILE.py").exists()
    assert (world["inputs"] / "stock_SYN.csv").read_text().endswith(ALLOWED_TEXT + "\n")
    assert not Path(world["canary"] + ".new").exists()


def test_privilege_escalation_primitives_denied(sandboxed):
    _, R = sandboxed
    assert not R["chroot"]["ok"] and not R["mount_syscall"]["ok"] and not R["unshare_userns"]["ok"]
    assert R["ids"]["value"] if "value" in R["ids"] else True
    assert R["ids"]["cap_eff"].strip("0") == ""


# ------------------------------------------------------------------ what is visible
def test_no_parent_or_secret_paths_visible(world, sandboxed):
    _, R = sandboxed
    assert R["tree:components_hit"] == []
    assert R["tree:in"] == ["grid_SYN.csv", "stock_SYN.csv"]          # parent dir contents/siblings absent
    assert R["tree:code"] == ["harness", "probe"]
    assert set(R["tree:home"]) == {"srinivas"}
    assert set(R["tree:home_srinivas"]) <= {".venvs", ".local"}      # runtime prefixes only; no secrets, repos, projects
    assert set(R["tree:top"]) <= {"code", "in", "out", "scratch", "tmp", "proc", "dev", "home", "usr", "lib", "lib64", "bin"}
    assert "etc" not in R["tree:top"] and "root" not in R["tree:top"] and "run" not in R["tree:top"]


def test_namespaces_fds_and_process_view(sandboxed):
    res, R = sandboxed
    assert R["ids"]["pid"] <= 16
    assert R["ids"]["hostname"] == "r5-isolated"
    extra = {k: v for k, v in R["fds_at_start"].items() if int(k) > 2 and not v.startswith("/proc/")}
    assert extra == {}, extra                               # only stdio (+ this listing's own dir fd) inherited
    assert R["fds_at_start"]["0"] == "/dev/null" and R["fds_at_start"]["1"].startswith("pipe:")
    w = res.witness
    for k in osi.NS_KINDS:
        assert w["child_ns"][k] != w["host_ns"][k]
    assert w["bwrap_info"]["child-pid"] > 0


# ------------------------------------------------------------------ mount plan (no broad mounts)
def test_runtime_and_input_mounts_are_narrow(world):
    plan = osi.build_plan(make_spec(world))
    srcs = [s for _, s, _ in plan.mounts]
    for broad in osi.BROAD_DENY:
        assert broad not in srcs, broad
    inputs_dir = str(world["inputs"])
    assert not any(s == inputs_dir or s == str(world["secret"]) for s in srcs)
    assert all(not (m[1].startswith(inputs_dir + "/") and m[2] != f"/in/{os.path.basename(m[1])}") for m in plan.mounts)
    ro_lib_files = [s for k, s, d in plan.mounts if k == "ro-bind" and os.path.isfile(s)]
    assert ro_lib_files and all(os.path.isfile(s) for s in ro_lib_files)       # libraries are file binds, never lib dirs
    allowed_dirs = {d for d in plan.runtime_dirs} | {str(HARNESS), str(world["probe_code"]), str(world["out"])}
    dir_binds = {s for k, s, d in plan.mounts if k in ("ro-bind", "bind") and os.path.isdir(s)}
    assert dir_binds == allowed_dirs
    audit = audit_plan(osi.build_argv(plan, 9), plan)
    assert [b for b in audit["binds"] if b[0] == "bind"] == [("bind", str(world["out"]), "/out")]


def audit_plan(argv, plan):
    return osi.audit_argv(argv, plan.protected, plan.no_expose)


@pytest.mark.parametrize("broad", ["/", "/home", "/home/srinivas", "/usr", "/etc", "/home/srinivas/projects",
                                   "/home/srinivas/R5_ENGINEERING_PLATFORM", "/home/srinivas/R5_ENGINEERING_PLATFORM/work",
                                   "/home/srinivas/projects/zerodha-r5-governor-refactor"])
def test_auditor_refuses_broad_ro_bind(world, broad):
    plan = osi.build_plan(make_spec(world))
    audit_plan(osi.build_argv(plan, 9), plan)                          # the genuine argv is accepted
    for dest in ("/host", broad):
        argv = osi.build_argv(plan, 9)
        i = argv.index("--remount-ro")
        argv[i:i] = ["--ro-bind", broad, dest]
        with pytest.raises(osi.BroadMountError):
            audit_plan(argv, plan)


def test_launch_refuses_broad_argv_before_starting_bwrap(world):
    for broad in ("/", "/home/srinivas", "/home", str(world["secret"].parent), str(world["secret"]),
                  "/home/srinivas/projects/zerodha-r5-governor-refactor"):
        def broaden(argv, broad=broad):
            i = argv.index("--remount-ro")
            return argv[:i] + ["--ro-bind", broad, "/hostroot"] + argv[i:]
        with pytest.raises(osi.BroadMountError):
            osi.launch(make_spec(world, args=("{}",)), _argv_hook=broaden)


def test_auditor_refuses_unshared_net_missing_flags_and_writable_binds(world):
    plan = osi.build_plan(make_spec(world))
    for flag in ("--unshare-net", "--unshare-user", "--unshare-pid", "--clearenv", "--die-with-parent", "--disable-userns"):
        argv = [a for a in osi.build_argv(plan, 9) if a != flag]
        with pytest.raises(osi.BroadMountError):
            audit_plan(argv, plan)
    for extra in (["--share-net"], ["--dev-bind", "/", "/x"], ["--bind", "/tmp/x", "/y"], ["--cap-add", "ALL"]):
        argv = osi.build_argv(plan, 9)
        argv[1:1] = extra
        with pytest.raises(osi.BroadMountError):
            audit_plan(argv, plan)
    argv = osi.build_argv(plan, 9)
    i = argv.index("--remount-ro")
    argv[i:i] = ["--bind", str(world["probe_code"]), "/scratch2"]
    with pytest.raises(osi.BroadMountError):
        audit_plan(argv, plan)


def test_spec_refuses_broad_code_input_or_output_roots(world, tmp_path):
    secret_parent = str(world["secret"].parent)
    with pytest.raises(osi.BroadMountError):
        osi.build_plan(make_spec(world, output_dir=secret_parent), host_precheck=False)
    with pytest.raises(osi.BroadMountError):
        osi.build_plan(make_spec(world, output_dir="/home/srinivas"), host_precheck=False)
    with pytest.raises(osi.OSIsolationError):
        osi.build_plan(make_spec(world, output_dir=str(world["root"] / "missing")), host_precheck=False)
    link = tmp_path / "out_link"
    link.symlink_to(world["out"])
    with pytest.raises(osi.OSIsolationError):
        osi.build_plan(make_spec(world, output_dir=str(link)), host_precheck=False)
    # code root that is an ancestor of the protected secret dir / repo
    for bad in ("/home/srinivas/R5_ENGINEERING_PLATFORM/work", "/home/srinivas/R5_ENGINEERING_PLATFORM"):
        roots = {"harness": str(HARNESS), "probe": bad}
        with pytest.raises(osi.BroadMountError):
            osi.build_plan(make_spec(world, code_roots=roots, code_pins={"harness": "0" * 64, "probe": "0" * 64}),
                           host_precheck=False)
    # an input must be a plain file, never the directory around it; protected-tree inputs are refused
    spec = make_spec(world)
    for bad in (osi.InputArtifact(str(world["inputs"]), "dir", "0" * 64, "x"),
                osi.InputArtifact(world["canary"], "canary", sha(world["canary"]), "x")):
        with pytest.raises(osi.OSIsolationError):
            osi.build_plan(osi.IsolationSpec(**{**spec.__dict__, "inputs": (bad,)}), host_precheck=False)


# ------------------------------------------------------------------ pins / bootstrap / witness
def test_wrong_code_pin_refused_before_launch(world):
    spec = make_spec(world)
    bad = osi.IsolationSpec(**{**spec.__dict__, "code_pins": {**spec.code_pins, "probe": "0" * 64}})
    with pytest.raises(osi.PinMismatch):
        osi.launch(bad)


def test_wrong_input_pin_refused_before_launch(world):
    spec = make_spec(world)
    a0 = spec.inputs[0]
    bad = osi.IsolationSpec(**{**spec.__dict__, "inputs": (osi.InputArtifact(a0.host_path, a0.alias, "1" * 64, "x"),) + spec.inputs[1:]})
    with pytest.raises(osi.PinMismatch):
        osi.launch(bad)


def test_wrong_pins_caught_inside_the_sandbox_when_host_precheck_is_bypassed(world):
    spec = make_spec(world, args=("{}",))
    bad_code = osi.IsolationSpec(**{**spec.__dict__, "code_pins": {**spec.code_pins, "probe": "0" * 64}})
    res = osi.launch(bad_code, host_precheck=False)
    assert res.status == "BOOTSTRAP_FAILED" and "code tree sha256 differs" in res.detail and "PROBE_JSON" not in res.stdout
    a0 = spec.inputs[0]
    bad_in = osi.IsolationSpec(**{**spec.__dict__, "inputs": (osi.InputArtifact(a0.host_path, a0.alias, "2" * 64, "x"),) + spec.inputs[1:]})
    res = osi.launch(bad_in, host_precheck=False)
    assert res.status == "BOOTSTRAP_FAILED" and "input sha256 differs" in res.detail and "PROBE_JSON" not in res.stdout


def test_forged_witness_rejected_by_bootstrap_and_target_never_runs(world):
    def forge_ns(hand):
        hand["expectation"]["child_ns"]["net"] = "net:[4026531840]"
        return hand

    def forge_nonce(hand):
        hand["witness"]["nonce"] = "0" * 32
        return hand

    def forge_mounts(hand):
        hand["expectation"]["mount_points"] = hand["expectation"]["mount_points"] + ["/home"]
        hand["expectation"]["root"] = hand["expectation"]["root"] + ["home"]
        return hand

    def garbage(hand):
        return {"nonce": "x"}

    for tamper in (forge_ns, forge_nonce, garbage):
        res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=("ok",)), _tamper=tamper)
        assert res.status == "BOOTSTRAP_FAILED", (tamper.__name__, res.status, res.stderr[-400:])
        assert "done" not in res.stdout and res.returncode == osi.BOOTSTRAP_FAIL_RC
    res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=("ok",)), _tamper=forge_mounts)
    assert res.status == "BOOTSTRAP_FAILED" and "expected mounts absent" in res.detail
    with pytest.raises(osi.WitnessError):
        osi.trusted_witness(res)


def test_missing_witness_handshake_fails_closed(world):
    # launcher "forgets" to send the handshake: closing stdin without a line must not run the target
    res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=("ok",)), _tamper=lambda hand: None)
    assert res.status in ("BOOTSTRAP_FAILED", "SANDBOX_SETUP_FAILED") and "done" not in res.stdout


def test_bootstrap_failure_when_environment_cannot_build_a_sandbox(world, monkeypatch):
    monkeypatch.setattr(osi, "BWRAP", "/usr/bin/does-not-exist")
    with pytest.raises(osi.UnsupportedEnvironment):
        osi.launch(make_spec(world, args=("{}",)))


def test_sandbox_setup_failure_is_reported_not_trusted(world):
    def break_bind(argv):
        i = argv.index("--ro-bind")
        argv[i + 1] = argv[i + 1] + "_does_not_exist"
        return argv
    res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=("ok",)), _argv_hook=break_bind)
    assert res.status == "SANDBOX_SETUP_FAILED" and res.witness is None and not res.ok
    with pytest.raises(osi.WitnessError):
        osi.trusted_witness(res)


@pytest.mark.parametrize("mode,status,rc", [("ok", "OK", 0), ("fail:3", "TARGET_FAILED", 3), ("raise", "TARGET_FAILED", 1),
                                             ("kill", "TARGET_SIGNALED", 137)])
def test_child_status_handling(world, mode, status, rc):
    res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=(mode,)))
    assert res.status == status, (res.status, res.detail, res.stderr[-500:])
    assert res.returncode == rc
    if status in ("OK", "TARGET_FAILED"):
        assert osi.trusted_witness(res)["profile"] == osi.PROFILE
    else:
        assert res.ok is False


def test_timeout_kills_the_whole_sandbox(world):
    res = osi.launch(make_spec(world, target="probe/probe_exit.py", args=("hang",), timeout_s=8))
    assert res.status == "TIMEOUT" and not res.ok


def test_harness_gate_sees_live_boundary_but_real_release_stays_closed(world):
    res = osi.launch(make_spec(world, target="probe/probe_witness.py"))
    R = parse(res)
    assert res.ok, (res.status, res.detail, res.stderr[-800:])
    assert R["active_witness_ok"] == dict(schema=osi.WITNESS_SCHEMA, reverified=True, verified=True)
    assert "OS-level boundary verified" in R["harness_gate"] and "release closed" in R["harness_gate"]
    assert R["fresh_process"] == "REFUSED"
    assert R["forged_expectation"] == "REFUSED" and R["cleared"] == "REFUSED"


def test_harness_gate_refuses_outside_any_launch():
    with pytest.raises(h.IsolationGateError, match="OS-level"):
        h.os_isolation_witness()
    with pytest.raises(osi.WitnessError):
        osi.active_witness()
    with pytest.raises(osi.WitnessError):
        osi.require_real_run_release({"profile": osi.PROFILE})


def test_authorization_json_cannot_open_the_gate(tmp_path):
    forged = tmp_path / "witness.json"
    forged.write_text(json.dumps(dict(schema=osi.WITNESS_SCHEMA, profile=osi.PROFILE, bootstrap_verified_live=True)))
    with pytest.raises(h.IsolationGateError):
        h.os_isolation_witness()
    osi._ACTIVE = dict(expectation=dict(child_ns={k: "x" for k in osi.NS_KINDS}, host_ns={}, mount_points=["/"], root=[],
                                        ro_mounts=[]), witness={})
    try:
        with pytest.raises(h.IsolationGateError):
            h.os_isolation_witness()           # live host state contradicts the forged expectation
    finally:
        osi._ACTIVE = None


def test_real_code_roots_pinned_and_mounted_read_only(world):
    """The audited harness dir and the audited snapshot tree are mounted read-only, pin-verified inside the sandbox."""
    roots = {"harness": str(HARNESS), "snapshot": str(PLATFORM / "snapshot"), "probe": str(world["probe_code"])}
    pins = {k: osi.tree_sha256(v) for k, v in roots.items()}
    cfg = dict(allowed=[], denied=[], write_denied=["/code/snapshot/revision2_external/indicators_talib.py",
                                                    "/code/snapshot/NEW.py"], forbidden_components=FORBIDDEN_COMPONENTS)
    spec = make_spec(world, args=(json.dumps(cfg),), code_roots=roots, code_pins=pins)
    before = osi.tree_sha256(PLATFORM / "snapshot")
    res = osi.launch(spec)
    R = parse(res)
    assert res.ok, (res.status, res.detail, res.stderr[-600:])
    assert res.witness["code_pins"]["snapshot"] == pins["snapshot"] == before
    assert not R["write_denied:builtins:/code/snapshot/NEW.py"]["ok"]
    assert not R["write_denied:os:/code/snapshot/revision2_external/indicators_talib.py"]["ok"]
    assert osi.tree_sha256(PLATFORM / "snapshot") == before
    assert R["tree:components_hit"] == []


# ------------------------------------------------------------------ independent syscall-level witness (strace)
def test_strace_syscall_log_shows_no_successful_access_outside_the_boundary(world, tmp_path):
    """Run the very same audited bwrap argv under /usr/bin/strace -f and inspect the kernel-level syscall results."""
    if not os.path.exists(osi.STRACE):
        pytest.skip("strace not installed")
    log = tmp_path / "strace.log"
    cfg = probe_cfg(world)
    res = osi.launch(make_spec(world, args=(json.dumps(cfg),)),
                     _prefix=(osi.STRACE, "-f", "-qq", "-s", "256", "-e", "trace=openat,open,connect,execve,mount,chroot",
                              "-o", str(log)))
    if res.status == "SANDBOX_SETUP_FAILED" and "ptrace" in res.stderr.lower():
        pytest.skip("ptrace not permitted in this environment")
    assert res.ok, (res.status, res.detail, res.stderr[-600:])
    text = log.read_text()
    assert text.count("\n") > 200
    secret_words = (str(world["secret"]), "zerodha-r5-governor-refactor", "/home/srinivas/.bashrc")
    inside = [ln for ln in text.splitlines() if any(w in ln for w in secret_words)
              and re.match(r"\d+\s+(openat|open|connect)\(", ln)]            # execve argv mentions are not accesses
    # every in-sandbox open/connect of a host-secret path (the denied probes) failed at the kernel
    bad = [ln for ln in inside if " = -1 " not in ln]
    assert bad == [], bad[:5]
    assert any(" = -1 ENOENT" in ln for ln in inside), "denied probes should be visible as failed syscalls"
    assert "CANARY" not in text
    connects = [ln for ln in text.splitlines() if re.match(r"\d+\s+connect\(", ln)]
    assert connects and all(" = -1 " in ln for ln in connects), connects      # every connect attempt failed in the kernel
    assert not any(len(ln) > 0 and re.match(r"\d+\s+connect\(", ln) and " = 0" in ln for ln in text.splitlines())
