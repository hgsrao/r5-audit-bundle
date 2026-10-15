"""WP-R5-004-OS-ISOLATION: minimal filesystem / network / process isolation launcher built on /usr/bin/bwrap.

The child namespace is built from an EMPTY tmpfs root. The host root, /home, the original repos and the raw stock/grid
repositories are never bound (not even read-only). Only these are exposed:

* explicit runtime paths: the interpreter's venv prefix and base prefix (read-only, same paths) plus the individual shared
  libraries reported by ``ldd`` for the interpreter and its extension modules (file binds, never a library directory);
* audited code roots (read-only, tree-sha256 pinned): e.g. harness dir and snapshot dir, mounted under /code/<name>;
* approved standalone input artifacts (read-only FILE binds under /in/<alias>, sha256 pinned; the parent directory is
  never mounted);
* one scoped writable output directory (/out) and a size-limited tmpfs scratch (/scratch), /tmp (tmpfs), /proc, /dev.

Namespaces: user, pid, net, ipc, uts, cgroup (all unshared; no network at all), nested user namespaces disabled,
all capabilities dropped, new session, ``--die-with-parent``, cleared environment. Descendants inherit all of it.

The witness is NOT a flag or JSON file: ``launch`` observes the running sandbox from the host (bwrap's own info-fd
namespace ids compared with the launcher's namespaces, ``/proc/<pid>`` view when readable) and the in-sandbox bootstrap
re-probes the live kernel state (namespace links, mountinfo, root listing, fds, capabilities, network interfaces) against
that host observation before running the target. ``active_witness`` re-probes again on every call; outside a launched,
verified sandbox it refuses. The real-data release stays closed regardless (``require_real_run_release``).

No data is read here. Subprocess use is limited to bwrap/ldd.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True

BWRAP = "/usr/bin/bwrap"
LDD = "/usr/bin/ldd"
STRACE = "/usr/bin/strace"
PROFILE = "WP004_OS_ISOLATION_V1"
WITNESS_SCHEMA = "WP004_OS_ISOLATION_WITNESS_V1"
CODE_MOUNT, IN_MOUNT, OUT_MOUNT, SCRATCH_MOUNT = "/code", "/in", "/out", "/scratch"
BOOTSTRAP_NAME = "os_isolation_bootstrap.py"
BOOTSTRAP_FAIL_RC = 97
NS_KINDS = ("mnt", "pid", "net", "ipc", "uts", "user", "cgroup")
INFO_NS_KEYS = {"mnt": "mnt-namespace", "pid": "pid-namespace", "net": "net-namespace", "ipc": "ipc-namespace",
                "uts": "uts-namespace", "cgroup": "cgroup-namespace"}
MARK_READY, MARK_START, MARK_END, MARK_FAIL = "@@WP004_READY", "@@WP004_TARGET_START", "@@WP004_TARGET_END", "@@WP004_BOOTSTRAP_FAILED"
SCRATCH_BYTES = 64 << 20
DEV_MOUNTS = frozenset(f"/dev/{n}" for n in ("null", "zero", "full", "random", "urandom", "tty", "pts", "shm", "console",
                                              "mqueue"))      # what bwrap --dev creates; device nodes only
MAX_HANDSHAKE = 1 << 20

# Directories that must never be bind sources (nor ancestors of protected paths): "broad" mounts.
BROAD_DENY = tuple(sorted({"/", "/home", "/root", "/etc", "/var", "/usr", "/usr/lib", "/usr/bin", "/lib", "/lib64", "/bin",
                           "/sbin", "/opt", "/mnt", "/media", "/srv", "/tmp", "/run", "/boot", "/sys", "/proc", "/dev",
                           "/home/srinivas", str(Path.home())}))
RELEASE_REQUIREMENTS = (
    "independently issued, hash-pinned TRAIN-only standalone input artifacts (stock + grid) whose bytes are exactly the "
    "authorized TRAIN/HEADER/warm-up intervals, with provenance distinct from the original raw files",
    "Director release acceptance record (hash-pinned in os_isolation.REAL_RUN_RELEASE_ACCEPTANCE_SHA256) naming this "
    "isolation profile, the code-tree pins, the input pins and the execution package",
    "an authorization whose roots/canonical_path/interval fields describe the curated artifacts as mounted in the sandbox",
    "a passing OS isolation test receipt for the exact launcher/bootstrap/harness hashes being released",
)
REAL_RUN_RELEASE_ACCEPTANCE_SHA256 = None   # None => real-data release closed. No code path opens it today.


class OSIsolationError(Exception):
    pass


class UnsupportedEnvironment(OSIsolationError):
    pass


class BroadMountError(OSIsolationError):
    pass


class PinMismatch(OSIsolationError):
    pass


class WitnessError(OSIsolationError):
    pass


# --------------------------------------------------------------------- hashing
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha256(root) -> str:
    """sha256 over sorted (relative path, file sha256) of every regular file; symlinks/specials refuse; __pycache__ ignored."""
    root, rows = Path(root), []
    for dp, dn, fn in os.walk(root, followlinks=False):
        dn[:] = sorted(d for d in dn if d != "__pycache__")
        for name in dn:
            if os.path.islink(os.path.join(dp, name)):
                raise PinMismatch(f"symlinked directory inside code root: {os.path.join(dp, name)}")
        for name in sorted(fn):
            p = os.path.join(dp, name)
            if not stat.S_ISREG(os.lstat(p).st_mode):
                raise PinMismatch(f"non-regular file inside code root: {p}")
            rows.append(f"{os.path.relpath(p, root)}\0{sha256_file(p)}\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()


# --------------------------------------------------------------------- environment
def check_environment() -> dict:
    """Fail closed (UnsupportedEnvironment) unless the launcher prerequisites are present. Does not launch anything."""
    if not sys.platform.startswith("linux"):
        raise UnsupportedEnvironment("linux required")
    for tool in (BWRAP, LDD):
        if not os.path.isfile(tool) or not os.access(tool, os.X_OK):
            raise UnsupportedEnvironment(f"{tool} missing or not executable")
    if os.stat(BWRAP).st_mode & stat.S_ISUID:
        raise UnsupportedEnvironment("setuid bwrap not supported: the unprivileged user-namespace path is required")
    out = subprocess.run([BWRAP, "--version"], capture_output=True, text=True, env={}, timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out.stdout)
    if out.returncode != 0 or not m or tuple(map(int, m.groups())) < (0, 8, 0):
        raise UnsupportedEnvironment(f"bwrap >= 0.8.0 required (--disable-userns): {out.stdout.strip()!r}")
    for kind in NS_KINDS:
        if not os.path.exists(f"/proc/self/ns/{kind}"):
            raise UnsupportedEnvironment(f"kernel lacks /proc/self/ns/{kind}")
    return dict(bwrap=BWRAP, bwrap_sha256=sha256_file(BWRAP), bwrap_version=out.stdout.strip(), uid=os.getuid(),
                kernel=os.uname().release)


def _is_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _symlinks_on_path(path: str) -> list:
    """Every symlink (as (location, link text)) met while resolving ``path`` (components and final file)."""
    out, pending = [], path
    for _ in range(40):
        parts, cur, hop = Path(pending).parts, "/", False
        for i, part in enumerate(parts[1:], 1):
            nxt = os.path.join(cur, part)
            if os.path.islink(nxt):
                text = os.readlink(nxt)
                out.append((nxt, text))
                tgt = text if os.path.isabs(text) else os.path.join(cur, text)
                pending, hop = os.path.normpath(os.path.join(tgt, *parts[i + 1:])), True
                break
            cur = nxt
        if not hop:
            return out
    raise UnsupportedEnvironment(f"symlink chain too deep: {path}")


@functools.lru_cache(maxsize=8)
def _runtime_layout(python: str):
    """Explicit runtime exposure for ``python``: (prefix dirs, [(real_path, dest)], symlink_pairs, root_symlinks)."""
    if not os.path.isabs(python) or not os.path.exists(python):
        raise UnsupportedEnvironment(f"interpreter must be an existing absolute path: {python}")
    out = subprocess.run([python, "-I", "-c", "import sys,json;print(json.dumps([sys.prefix,sys.base_prefix]))"],
                         capture_output=True, text=True, env={}, timeout=60)
    if out.returncode != 0:
        raise UnsupportedEnvironment(f"interpreter probe failed: {out.stderr.strip()}")
    prefix, base = (os.path.realpath(p) for p in json.loads(out.stdout))
    dirs = sorted({prefix, base})
    real_py = os.path.realpath(python)
    if not any(_is_under(real_py, d) for d in dirs) and not _is_under(real_py, "/usr"):
        raise UnsupportedEnvironment(f"interpreter {real_py} outside its prefix dirs {dirs}")
    elfs = {real_py}
    for d in dirs:
        for dp, dn, fn in os.walk(d):
            elfs.update(os.path.realpath(os.path.join(dp, f)) for f in fn if f.endswith(".so") or ".so." in f)
    libs, links, root_links = {}, {}, {}
    for elf in sorted(elfs):
        r = subprocess.run([LDD, elf], capture_output=True, text=True, env={}, timeout=60)
        if r.returncode != 0 and "not a dynamic executable" not in (r.stdout + r.stderr):
            continue   # non-ELF look-alike (e.g. text); a genuinely unresolved lib is caught below
        for line in r.stdout.splitlines():
            if "not found" in line:
                if elf == real_py:
                    raise UnsupportedEnvironment(f"unresolved shared library for the interpreter: {line.strip()}")
                continue    # optional extension (e.g. _tkinter) with a missing host lib: simply not importable in the sandbox
            m = re.search(r"(?:=>\s*)?(/\S+)\s+\(0x", line)
            if not m:
                continue
            p = m.group(1)
            real = os.path.realpath(p)
            if any(_is_under(real, d) for d in dirs):
                continue
            libs[real] = real
            dest = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
            if dest != real:
                links[dest] = real
            top = "/" + p.split("/")[1]
            if os.path.islink(top):
                root_links[top] = os.readlink(top)
    for loc, text in _symlinks_on_path(python):      # e.g. venv bin/python -> uv alias dir -> real interpreter dir
        if not any(_is_under(loc, d) for d in dirs):
            root_links[loc] = text
    return tuple(dirs), tuple(sorted(libs.items())), tuple(sorted(links.items())), tuple(sorted(root_links.items()))


# --------------------------------------------------------------------- spec / plan
@dataclass(frozen=True)
class InputArtifact:
    host_path: str       # approved standalone TRAIN-only artifact (a FILE; its directory is never mounted)
    alias: str           # mounted as /in/<alias>
    sha256: str
    approval_id: str     # identifier of the external approval of this artifact (recorded in the witness; not verified here)


@dataclass(frozen=True)
class IsolationSpec:
    python: str
    code_roots: dict                  # name -> host dir (read-only at /code/<name>)
    code_pins: dict                   # name -> tree sha256 (must cover every code root)
    target: str                       # script path relative to /code, e.g. "harness/probe.py"
    target_args: tuple = ()
    inputs: tuple = ()
    output_dir: str = ""
    protected_paths: tuple = ()       # secret / original-repo / raw-data trees: never bound, contained or exposed
    no_expose_paths: tuple = ()       # directories whose own listing must stay hidden (e.g. project root); children may bind
    bootstrap_root: str = "harness"   # code root holding os_isolation.py + os_isolation_bootstrap.py
    timeout_s: float = 120.0


def _real(path) -> str:
    return os.path.realpath(path)


def _check_not_broad(src: str, label: str, protected, no_expose):
    """``protected``: trees that may be neither bound, contained in a bind, nor exposed by an ancestor bind (secrets,
    original repos, raw data roots). ``no_expose``: directories that must not be bound or have an ancestor-or-equal bound
    (home, an input's parent dir, the project root), but whose explicitly listed descendants may be."""
    if src in BROAD_DENY:
        raise BroadMountError(f"{label}: broad mount source refused: {src}")
    for p in protected:
        if p == src or _is_under(p, src) or _is_under(src, p):
            raise BroadMountError(f"{label}: {src} overlaps protected path {p} (ancestor/descendant/equal)")
    for p in no_expose:
        if p == src or _is_under(p, src):
            raise BroadMountError(f"{label}: {src} would expose {p}")


@dataclass(frozen=True)
class Plan:
    spec: IsolationSpec
    runtime_dirs: tuple
    runtime_libs: tuple
    mounts: tuple          # ((kind, src, dest)) for audit/receipt: kind in ro-bind/bind/tmpfs/proc/dev/symlink
    protected: tuple
    no_expose: tuple


def _protected_sets(spec: IsolationSpec):
    prot = sorted({_real(p) for p in spec.protected_paths})
    exp = {_real(str(Path.home())), "/home", "/root", *(_real(p) for p in spec.no_expose_paths)}
    for a in spec.inputs:
        exp.add(_real(os.path.dirname(a.host_path)))        # an input's parent directory is never mountable
    return prot, sorted(exp)


def build_plan(spec: IsolationSpec, *, host_precheck: bool = True) -> Plan:
    check_environment()
    if not os.path.isabs(spec.python):
        raise OSIsolationError("python must be absolute")
    protected, no_expose = _protected_sets(spec)
    dirs, libs, links, root_links = _runtime_layout(spec.python)
    mounts = []
    for d in dirs:
        _check_not_broad(d, "runtime dir", protected, no_expose)
        mounts.append(("ro-bind", d, d))
    for real, dest in libs:
        mounts.append(("ro-bind", real, real))
    for dest, real in links:
        mounts.append(("symlink", real, dest))
    for top, target in root_links:
        mounts.append(("symlink", target, top))
    if set(spec.code_roots) != set(spec.code_pins):
        raise PinMismatch("code_pins must cover exactly the code roots")
    if spec.bootstrap_root not in spec.code_roots:
        raise OSIsolationError("bootstrap_root must be one of the code roots")
    for name, host in sorted(spec.code_roots.items()):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise OSIsolationError(f"bad code root name {name!r}")
        src = _real(host)
        if src != str(host) or not os.path.isdir(src) or os.path.islink(host):
            raise OSIsolationError(f"code root must be a real, already-resolved directory: {host}")
        _check_not_broad(src, f"code root {name}", protected, no_expose)
        if host_precheck and tree_sha256(src) != spec.code_pins[name]:
            raise PinMismatch(f"code root {name}: tree sha256 differs from pin")
        mounts.append(("ro-bind", src, f"{CODE_MOUNT}/{name}"))
    for need in ("os_isolation.py", BOOTSTRAP_NAME):
        if not os.path.isfile(os.path.join(spec.code_roots[spec.bootstrap_root], need)):
            raise OSIsolationError(f"bootstrap root lacks {need}")
    if not spec.target.startswith(tuple(f"{n}/" for n in spec.code_roots)):
        raise OSIsolationError("target must live under a pinned code root")
    aliases = set()
    for a in spec.inputs:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.alias) or a.alias in aliases:
            raise OSIsolationError(f"bad/duplicate input alias {a.alias!r}")
        aliases.add(a.alias)
        if not a.approval_id or not isinstance(a.approval_id, str):
            raise OSIsolationError(f"{a.alias}: approval_id missing")
        if not os.path.isabs(a.host_path) or os.path.islink(a.host_path) or not os.path.isfile(a.host_path):
            raise OSIsolationError(f"{a.alias}: input must be an absolute plain file (no symlink)")
        src = _real(a.host_path)
        if src != a.host_path:
            raise OSIsolationError(f"{a.alias}: input path must be already resolved")
        for p in protected:
            if p == src or _is_under(src, p):
                raise BroadMountError(f"{a.alias}: input lies inside protected path {p}")
        if not re.fullmatch(r"[0-9a-f]{64}", a.sha256):
            raise PinMismatch(f"{a.alias}: malformed sha256 pin")
        if host_precheck and sha256_file(src) != a.sha256:
            raise PinMismatch(f"{a.alias}: input sha256 differs from pin")
        mounts.append(("ro-bind", src, f"{IN_MOUNT}/{a.alias}"))
    out = spec.output_dir
    if not out or not os.path.isabs(out) or os.path.islink(out) or not os.path.isdir(out) or _real(out) != out:
        raise OSIsolationError("output_dir must be an existing, resolved, non-symlink absolute directory")
    _check_not_broad(out, "output dir", protected, no_expose)
    for name, host in spec.code_roots.items():
        if _is_under(out, host) or _is_under(host, out):
            raise BroadMountError("output dir overlaps a code root (source writes must stay impossible)")
    for a in spec.inputs:
        if _is_under(a.host_path, out):
            raise BroadMountError("output dir contains an input artifact")
    mounts.append(("bind", out, OUT_MOUNT))
    return Plan(spec=spec, runtime_dirs=dirs, runtime_libs=tuple(r for r, _ in libs), mounts=tuple(mounts),
                protected=tuple(protected), no_expose=tuple(no_expose))


def build_argv(plan: Plan, info_fd: int) -> list:
    a = [BWRAP, "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup",
         "--disable-userns", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL",
         "--hostname", "r5-isolated", "--info-fd", str(info_fd),
         "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--size", str(SCRATCH_BYTES), "--tmpfs", SCRATCH_MOUNT]
    for kind, src, dest in plan.mounts:
        a += [f"--{kind}", src, dest] if kind != "symlink" else ["--symlink", src, dest]
    a += ["--remount-ro", "/",
          "--setenv", "HOME", SCRATCH_MOUNT, "--setenv", "TMPDIR", "/tmp", "--setenv", "LC_ALL", "C.UTF-8",
          "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "PYTHONNOUSERSITE", "1",
          "--chdir", SCRATCH_MOUNT, "--",
          plan.spec.python, "-I", "-B", f"{CODE_MOUNT}/{plan.spec.bootstrap_root}/{BOOTSTRAP_NAME}"]
    return a


# bwrap options accepted by the auditor (name -> number of arguments); anything else is refused (fail closed)
_ARITY = {"--unshare-user": 0, "--unshare-pid": 0, "--unshare-net": 0, "--unshare-ipc": 0, "--unshare-uts": 0,
          "--unshare-cgroup": 0, "--disable-userns": 0, "--die-with-parent": 0, "--new-session": 0, "--clearenv": 0,
          "--cap-drop": 1, "--hostname": 1, "--info-fd": 1, "--proc": 1, "--dev": 1, "--tmpfs": 1, "--size": 1,
          "--ro-bind": 2, "--bind": 2, "--symlink": 2, "--remount-ro": 1, "--setenv": 2, "--chdir": 1}
_REQUIRED_FLAGS = ("--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup",
                   "--disable-userns", "--die-with-parent", "--new-session", "--clearenv")


def audit_argv(argv, protected=(), no_expose=()) -> dict:
    """Independent parse of a bwrap argv. Refuses broad/unknown/unsafe mounts and missing isolation flags.
    Returns {'binds': [(kind, src, dest)], 'mount_points': set, 'command': [...]}."""
    if not argv or argv[0] != BWRAP:
        raise BroadMountError("argv[0] must be /usr/bin/bwrap")
    prot = [_real(p) for p in protected]
    seen, binds, mount_points, i = [], [], {"/"}, 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if tok not in _ARITY:
            raise BroadMountError(f"unknown or forbidden bwrap option: {tok}")
        n = _ARITY[tok]
        args = argv[i + 1:i + 1 + n]
        if len(args) != n:
            raise BroadMountError(f"{tok}: missing arguments")
        seen.append(tok)
        if tok in ("--ro-bind", "--bind"):
            src, dest = args
            if not os.path.isabs(src) or ".." in Path(src).parts or not os.path.isabs(dest):
                raise BroadMountError(f"relative bind path: {args}")
            if dest == "/" or dest in ("/proc", "/dev", "/tmp", SCRATCH_MOUNT):
                raise BroadMountError(f"bind over reserved destination {dest}")
            _check_not_broad(_real(src), tok, prot, [_real(p) for p in no_expose])
            if tok == "--bind" and dest != OUT_MOUNT:
                raise BroadMountError("only the output directory may be writable")
            binds.append((tok[2:], src, dest))
            mount_points.add(dest)
        elif tok in ("--tmpfs", "--proc", "--dev"):
            mount_points.add(args[0])
            if tok == "--dev":
                mount_points |= DEV_MOUNTS
        elif tok == "--cap-drop" and args != ["ALL"]:
            raise BroadMountError("only --cap-drop ALL is accepted")
        i += 1 + n
    for flag in _REQUIRED_FLAGS:
        if flag not in seen:
            raise BroadMountError(f"required isolation flag missing: {flag}")
    if "--share-net" in argv:
        raise BroadMountError("network must not be shared")
    if not any(argv[j] == "--cap-drop" and argv[j + 1] == "ALL" for j in range(len(argv) - 1)):
        raise BroadMountError("--cap-drop ALL missing")
    return dict(binds=binds, mount_points=mount_points, command=list(argv[i:]))


# --------------------------------------------------------------------- live probing (host and sandbox side)
def _unescape(s: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


def parse_mountinfo(text: str) -> list:
    rows = []
    for line in text.splitlines():
        f = line.split()
        if "-" not in f:
            continue
        sep = f.index("-")
        rows.append(dict(mount_point=_unescape(f[4]), options=f[5].split(","), fstype=f[sep + 1]))
    return rows


def probe_self() -> dict:
    """Live kernel view from inside the process (no trust in any file the launcher supplied)."""
    fds = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            fds[name] = os.readlink(f"/proc/self/fd/{name}")
        except OSError:
            pass   # the listing fd itself
    status = dict(line.split(":\t", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":\t" in line)
    ifaces = [ln.split(":")[0].strip() for ln in Path("/proc/net/dev").read_text().splitlines()[2:]]
    return dict(
        ns={k: os.readlink(f"/proc/self/ns/{k}") for k in NS_KINDS},
        mounts=parse_mountinfo(Path("/proc/self/mountinfo").read_text()),
        root=sorted(os.listdir("/")), fds=fds, cap_eff=status.get("CapEff", "").strip(),
        no_new_privs=status.get("NoNewPrivs", "").strip(), ifaces=ifaces, pid=os.getpid(), uid=os.getuid())


def _read_nsids(pid) -> dict:
    return {k: os.readlink(f"/proc/{pid}/ns/{k}") for k in NS_KINDS}


def verify_probe(probe: dict, exp: dict) -> list:
    """Compare a live probe with the host observation/plan; returns the list of violations (empty = boundary holds)."""
    bad = []
    for k in NS_KINDS:
        if probe["ns"].get(k) != exp["child_ns"].get(k):
            bad.append(f"ns {k}: {probe['ns'].get(k)} != host-observed {exp['child_ns'].get(k)}")
        if probe["ns"].get(k) == exp["host_ns"].get(k):
            bad.append(f"ns {k}: identical to the launcher's namespace (not isolated)")
    points = {m["mount_point"]: m for m in probe["mounts"]}
    extra = sorted(set(points) - set(exp["mount_points"]))
    if extra:
        bad.append(f"unexpected mounts: {extra[:8]}")
    missing = sorted(set(exp["mount_points"]) - set(points) - DEV_MOUNTS)
    if missing:
        bad.append(f"expected mounts absent: {missing[:8]}")
    for dest in exp["ro_mounts"]:
        if dest in points and "ro" not in points[dest]["options"]:
            bad.append(f"{dest} is writable but planned read-only")
    if probe["root"] != sorted(exp["root"]):
        bad.append(f"root listing {probe['root']} != planned {sorted(exp['root'])}")
    for fd, target in probe["fds"].items():
        if int(fd) > 2 and target != f"/proc/{probe['pid']}/fd":     # the directory fd used for this very listing
            bad.append(f"inherited fd {fd} -> {target}")
        if int(fd) <= 2 and not (target.startswith(("pipe:", "socket:")) or target.startswith("/dev/")):
            bad.append(f"stdio fd {fd} -> {target}")
    if probe["cap_eff"].strip("0") != "":
        bad.append(f"effective capabilities not empty: {probe['cap_eff']}")
    if probe["no_new_privs"] != "1":
        bad.append("no_new_privs not set")
    if [i for i in probe["ifaces"] if i != "lo"]:
        bad.append(f"network interfaces present: {probe['ifaces']}")
    if probe["pid"] > 16:
        bad.append(f"pid {probe['pid']} suggests the host pid namespace")
    return bad


# Sandbox-side state (set only by the bootstrap after it verified the live boundary and the pins).
_ACTIVE: dict | None = None


def activate(expectation: dict, witness: dict):
    global _ACTIVE
    _ACTIVE = dict(expectation=expectation, witness=witness)


def active_witness() -> dict:
    """Re-probe the live sandbox against the host observation recorded at launch. Refuses outside a verified launch."""
    if _ACTIVE is None:
        raise WitnessError("process was not started by the verified bwrap launcher bootstrap (no OS-level boundary witness)")
    bad = verify_probe(probe_self(), _ACTIVE["expectation"])
    if bad:
        raise WitnessError("live OS boundary no longer matches the host observation: " + "; ".join(bad))
    return dict(_ACTIVE["witness"], reverified_live=True)


def require_real_run_release(witness: dict):
    """The release gate. Closed: no release acceptance record exists, so even a verified boundary does not open real data."""
    if REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None:
        raise WitnessError("real-data release closed: no Director release acceptance record / trusted TRAIN-only input "
                           "artifacts exist; required: " + " | ".join(RELEASE_REQUIREMENTS))
    raise WitnessError("release acceptance verification is not implemented (fails closed)")


# --------------------------------------------------------------------- launcher
@dataclass
class LaunchResult:
    status: str                      # OK | TARGET_FAILED | TARGET_SIGNALED | BOOTSTRAP_FAILED | SANDBOX_SETUP_FAILED
    #                                # | HOST_VERIFICATION_FAILED | TIMEOUT
    returncode: int | None
    stdout: str
    stderr: str
    detail: str = ""
    witness: dict | None = None
    argv: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "OK"


class _Pump(threading.Thread):
    def __init__(self, stream, ready_marker=None):
        super().__init__(daemon=True)
        self.stream, self.buf, self.ready = stream, [], threading.Event()
        self.marker = ready_marker
        self.start()

    def run(self):
        for raw in iter(self.stream.readline, b""):
            line = raw.decode("utf-8", "replace")
            self.buf.append(line)
            if self.marker and line.startswith(self.marker):
                self.ready.set()
        self.ready.set()

    def text(self):
        return "".join(self.buf)


def _marker_json(text: str, marker: str):
    for line in text.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):].strip().rstrip("@"))
    return None


def launch(spec: IsolationSpec, *, host_precheck: bool = True, _tamper=None, _argv_hook=None,
           _prefix=()) -> LaunchResult:
    """Launch the spec's target inside the bwrap boundary and return a LaunchResult.

    Pre-launch spec violations raise OSIsolationError subclasses; everything after the process starts is reported as a
    status. ``_tamper``/``_argv_hook`` exist only so tests can forge the handshake / feed a broad argv to the auditor;
    ``_prefix`` lets tests run the audited bwrap argv under ``strace`` as an independent syscall-level witness."""
    plan = build_plan(spec, host_precheck=host_precheck)
    info_r, info_w = os.pipe()
    argv = build_argv(plan, info_w)
    if _argv_hook:
        argv = _argv_hook(argv)
    audit = audit_argv(argv, plan.protected, plan.no_expose)
    nonce = secrets.token_hex(16)
    proc = subprocess.Popen([*_prefix, *argv], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={},
                            close_fds=True, pass_fds=(info_w,), start_new_session=True, cwd="/")
    os.close(info_w)
    out_pump, err_pump = _Pump(proc.stdout), _Pump(proc.stderr, MARK_READY)

    def finish(status, detail="", witness=None):
        try:
            proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        proc.wait()
        out_pump.join(5), err_pump.join(5)
        rc = proc.returncode
        return LaunchResult(status, rc, out_pump.text(), err_pump.text(), detail, witness, argv)

    deadline = time.monotonic() + spec.timeout_s
    info = _read_info(info_r, deadline)
    if "child-pid" not in info:
        rc = proc.wait(timeout=max(1, deadline - time.monotonic()))
        out_pump.join(5), err_pump.join(5)
        return LaunchResult("SANDBOX_SETUP_FAILED", rc, out_pump.text(), err_pump.text(),
                            "bwrap did not report a sandbox (unsupported environment?)", None, argv)
    if not err_pump.ready.wait(max(0.1, deadline - time.monotonic())):
        return finish("TIMEOUT", "bootstrap never became ready")
    ready = _marker_json(err_pump.text(), MARK_READY)
    if ready is None:
        return _classify_end(proc, out_pump, err_pump, argv, deadline, finish, nonce, None)
    host_ns = _read_nsids("self")
    child_ns = {k: ready["ns"][k] for k in NS_KINDS}
    problems = []
    for k, key in INFO_NS_KEYS.items():       # bwrap's own report of the namespaces it created
        want = f"{k}:[{info.get(key)}]"
        if info.get(key) is None or want != child_ns[k]:
            problems.append(f"{k}: bwrap info {want} != child {child_ns[k]}")
    if [k for k in NS_KINDS if child_ns[k] == host_ns[k]]:
        problems.append("namespace shared with launcher: " + ",".join(k for k in NS_KINDS if child_ns[k] == host_ns[k]))
    pid = info["child-pid"]
    proc_view = {}
    try:        # independent host-side view of the live sandbox (when /proc/<pid> is readable to us)
        proc_view = dict(ns=_read_nsids(pid), mounts=parse_mountinfo(Path(f"/proc/{pid}/mountinfo").read_text()))
        if proc_view["ns"] != child_ns:
            problems.append("/proc/<pid>/ns differs from the child's self-report")
        hm = {m["mount_point"] for m in proc_view["mounts"]}
        if hm - audit["mount_points"]:
            problems.append(f"host-observed unexpected mounts: {sorted(hm - audit['mount_points'])[:8]}")
    except OSError:
        proc_view = {}
    top = sorted({d.split("/")[1] for d in audit["mount_points"] if d != "/"} | {m[2].split("/")[1] for m in plan.mounts})
    exp = dict(child_ns=child_ns, host_ns=host_ns, mount_points=sorted(audit["mount_points"]), root=top,
               ro_mounts=sorted(d for k, _, d in audit["binds"] if k == "ro-bind"))
    if problems:
        return finish("HOST_VERIFICATION_FAILED", "; ".join(problems))
    witness = dict(
        schema=WITNESS_SCHEMA, profile=PROFILE, nonce=nonce, launcher_pid=os.getpid(), bwrap_child_pid=pid,
        argv_sha256=hashlib.sha256(json.dumps(argv).encode()).hexdigest(), host_ns=host_ns, child_ns=child_ns,
        bwrap_info=info, host_proc_view_available=bool(proc_view), mount_points=exp["mount_points"],
        root_listing=top, code_pins=dict(spec.code_pins),
        inputs={a.alias: dict(sha256=a.sha256, approval_id=a.approval_id) for a in spec.inputs},
        runtime_dirs=list(plan.runtime_dirs), runtime_lib_files=list(plan.runtime_libs), network="unshared (no interfaces)",
        bootstrap_exe=f"{CODE_MOUNT}/{spec.bootstrap_root}/{BOOTSTRAP_NAME}")
    hand = dict(nonce=nonce, expectation=exp, witness=witness, code_pins=spec.code_pins,
                inputs={a.alias: a.sha256 for a in spec.inputs}, target=f"{CODE_MOUNT}/{spec.target}",
                target_args=list(spec.target_args))
    if _tamper:
        hand = _tamper(hand)
    try:
        if hand is not None:        # (tests: None = the launcher sends no handshake at all)
            proc.stdin.write((json.dumps(hand) + "\n").encode())
            proc.stdin.flush()
        proc.stdin.close()
    except OSError:
        pass
    return _classify_end(proc, out_pump, err_pump, argv, deadline, finish, nonce, witness)


def _read_info(fd: int, deadline: float) -> dict:
    """bwrap's --info-fd JSON. Parse as soon as it is complete (a tracer such as strace may keep the pipe open, so EOF
    is not required); EOF without a document means bwrap failed before creating the sandbox."""
    import select
    raw = b""
    try:
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], 0.2)[0]:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw += chunk
            try:
                return json.loads(raw.decode())
            except ValueError:
                continue
    finally:
        os.close(fd)
    return {}


def _classify_end(proc, out_pump, err_pump, argv, deadline, finish, nonce, witness):
    try:
        rc = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return finish("TIMEOUT", "deadline exceeded", witness)
    out_pump.join(5), err_pump.join(5)
    out, err = out_pump.text(), err_pump.text()
    fail = _marker_json(err, MARK_FAIL)
    started = any(ln.startswith(MARK_START) for ln in err.splitlines())
    ended = _marker_json(err, MARK_END)
    mk = lambda status, detail="": LaunchResult(status, rc, out, err, detail, witness, argv)   # noqa: E731
    if fail is not None:
        return mk("BOOTSTRAP_FAILED", json.dumps(fail))
    if not started:
        return mk("BOOTSTRAP_FAILED" if witness else "SANDBOX_SETUP_FAILED", "bootstrap did not reach the target")
    if ended is None:
        sig = rc - 128 if rc and rc > 128 else None
        return mk("TARGET_SIGNALED", f"target ended without completing (signal {sig})" if sig else "target ended abnormally")
    if ended.get("rc") != 0:
        return mk("TARGET_FAILED", f"target exit code {ended.get('rc')}")
    return mk("OK" if rc == 0 else "TARGET_FAILED", "" if rc == 0 else f"bwrap exit {rc}")


def trusted_witness(result: LaunchResult) -> dict:
    """Host-side acceptance of a launch as an OS-boundary witness: only a launched, host-verified, bootstrap-passed run."""
    if result.witness is None or result.status not in ("OK", "TARGET_FAILED"):
        raise WitnessError(f"no OS-boundary witness: launch status {result.status}")
    return result.witness
