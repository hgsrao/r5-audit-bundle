"""Sandbox-side probe for the OS-isolation tests. SYNTHETIC canaries only; no market data. Prints one JSON line.

Run either inside the bwrap boundary (via the launcher) or on the host as a negative control (``--control``).
argv[1] = JSON config (host paths of canaries / listener, allowed input paths as seen by this process).
"""
import builtins
import ctypes
import json
import mmap
import os
import socket
import subprocess
import sys

cfg = json.loads(sys.argv[1])
R = {}
R["fds_at_start"] = {n: os.readlink(f"/proc/self/fd/{n}") for n in os.listdir("/proc/self/fd") if os.path.lexists(f"/proc/self/fd/{n}")}


def attempt(label, fn):
    try:
        R[label] = dict(ok=True, value=fn())
    except BaseException as exc:      # noqa: BLE001 - the probe records every failure mode
        R[label] = dict(ok=False, error=type(exc).__name__, errno=getattr(exc, "errno", None))


libc = ctypes.CDLL(None, use_errno=True)
libc.open.argtypes, libc.open.restype = [ctypes.c_char_p, ctypes.c_int], ctypes.c_int
libc.syscall.restype = ctypes.c_long


def lc_open(path):
    fd = libc.open(path.encode(), os.O_RDONLY)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "libc open")
    data = os.read(fd, 64)
    os.close(fd)
    return data.decode()


def raw_openat(path):
    fd = libc.syscall(257, -100, path.encode(), os.O_RDONLY, 0)     # SYS_openat on x86_64
    if fd < 0:
        raise OSError(ctypes.get_errno(), "syscall openat")
    os.close(fd)
    return "opened"


def mm(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        with mmap.mmap(fd, 0, prot=mmap.PROT_READ) as m:
            return m[:64].decode()
    finally:
        os.close(fd)


def os_read(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        return os.read(fd, 64).decode()
    finally:
        os.close(fd)


def py_open(path):
    with builtins.open(path) as f:
        return f.read(64)


def sub_py(path):
    r = subprocess.run([sys.executable, "-I", "-c", "import sys;open(sys.argv[1]).read(1)", path],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        raise OSError(2, r.stderr.decode()[-120:])
    return "child-read"


def sub_shell(path):
    return subprocess.run(["/bin/cat", path], capture_output=True, timeout=20).stdout.decode()


def forked(path):
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            open(path).read(1)
            os.write(w, b"1")
        except OSError:
            os.write(w, b"0")
        os._exit(0)
    os.waitpid(pid, 0)
    flag = os.read(r, 1)
    if flag != b"0":
        return "child-read"
    raise OSError(2, "forked child denied")


def dotdot(path):
    os.chdir("/")
    return py_open("../" * 30 + path.lstrip("/"))


def proc_root(path):
    return py_open("/proc/self/root" + path)


def proc1_root(path):
    return py_open("/proc/1/root" + path)


READERS = dict(builtins_open=py_open, os_open=os_read, mmap=mm, ctypes_libc=lc_open, raw_syscall=raw_openat,
               subprocess_python=sub_py, subprocess_shell=sub_shell, fork_child=forked, dotdot=dotdot,
               proc_self_root=proc_root, proc_1_root=proc1_root)
for path in cfg.get("allowed", []):
    for name in ("builtins_open", "os_open", "mmap", "ctypes_libc", "subprocess_python", "fork_child"):
        if name == "fork_child":
            continue
        attempt(f"allowed:{name}:{os.path.basename(path)}", lambda p=path, n=name: READERS[n](p))
for path in cfg.get("denied", []):
    for name, fn in READERS.items():
        attempt(f"denied:{name}:{path}", lambda p=path, f=fn: f(p))
    attempt(f"denied:listdir:{path}", lambda p=path: os.listdir(os.path.dirname(p)))


def tcp(addr):
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(tuple(addr))
        return "connected"
    finally:
        s.close()


def unix(path):
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(path)
        return "connected"
    finally:
        s.close()


def sub_net(addr):
    r = subprocess.run([sys.executable, "-I", "-c",
                        "import socket,sys;s=socket.socket();s.settimeout(3);s.connect((sys.argv[1],int(sys.argv[2])))",
                        addr[0], str(addr[1])], capture_output=True, timeout=30)
    if r.returncode != 0:
        raise OSError(101, r.stderr.decode()[-120:])
    return "child-connected"


if cfg.get("tcp"):
    attempt("net:tcp_loopback_listener", lambda: tcp(cfg["tcp"]))
    attempt("net:subprocess_tcp", lambda: sub_net(cfg["tcp"]))
if cfg.get("unix"):
    attempt("net:unix_socket", lambda: unix(cfg["unix"]))
attempt("net:ifaces", lambda: sorted(n for _, n in socket.if_nameindex()))


def write(path, data="x"):
    with open(path, "w") as f:
        f.write(data)
    return "written"


def write_os(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    os.write(fd, b"x")
    os.close(fd)
    return "written"


for path in cfg.get("write_ok", []):
    attempt(f"write_ok:builtins:{path}", lambda p=path: write(p, "isolated output"))
    attempt(f"write_ok:os:{path}.os", lambda p=path: write_os(p + ".os"))
for path in cfg.get("write_denied", []):
    attempt(f"write_denied:builtins:{path}", lambda p=path: write(p))
    attempt(f"write_denied:os:{path}", lambda p=path: write_os(p))
    attempt(f"write_denied:subprocess:{path}", lambda p=path: subprocess.run(
        [sys.executable, "-I", "-c", "import sys;open(sys.argv[1],'w').write('x')", p], capture_output=True,
        timeout=30, check=True) and "written")
attempt("write_denied:root", lambda: write("/rootfile"))
attempt("chroot", lambda: os.chroot("/"))
attempt("mount_syscall", lambda: libc.mount(b"x", b"/mnt", b"tmpfs", 0, None) == 0 or (_ for _ in ()).throw(
    OSError(ctypes.get_errno(), "mount")))
attempt("unshare_userns", lambda: libc.unshare(0x10000000) == 0 or (_ for _ in ()).throw(
    OSError(ctypes.get_errno(), "unshare")))


def walk_all():
    names, dirs = set(), []
    for dp, dn, fn in os.walk("/", followlinks=False):
        if dp.startswith(("/proc", "/dev")):
            dn[:] = []
            continue
        dirs.append(dp)
        names.update(dp.split("/"))
        names.update(fn)
    return dict(components=sorted(names), dirs=dirs)


tree = walk_all()
R["tree:components_hit"] = sorted(set(tree["components"]) & set(cfg.get("forbidden_components", [])))
R["tree:top"] = sorted(os.listdir("/"))
R["tree:home"] = sorted(os.listdir("/home")) if os.path.isdir("/home") else None
R["tree:home_srinivas"] = sorted(os.listdir("/home/srinivas")) if os.path.isdir("/home/srinivas") else None
R["tree:in"] = sorted(os.listdir("/in")) if os.path.isdir("/in") else None
R["tree:code"] = sorted(os.listdir("/code")) if os.path.isdir("/code") else None
R["tree:dirs_outside_runtime"] = sorted(d for d in tree["dirs"] if not d.startswith(tuple(cfg.get("runtime_prefixes", ["/usr"])))
                                        and not d.startswith(("/code/", "/in")))
R["fds"] = {n: os.readlink(f"/proc/self/fd/{n}") for n in os.listdir("/proc/self/fd") if os.path.exists(f"/proc/self/fd/{n}")}
R["ids"] = dict(uid=os.getuid(), gid=os.getgid(), pid=os.getpid(), hostname=socket.gethostname(),
                cap_eff=[ln for ln in open("/proc/self/status") if ln.startswith("CapEff")][0].split()[1])
print("PROBE_JSON:" + json.dumps(R))
