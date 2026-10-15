"""Exploration (host, synthetic): who leaves epoll/pipe fds open after the engine run? Traces epoll/pipe creation."""
import os
import select
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, "/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/harness_tests")
import integration_world as iw  # noqa: E402
import wp004_train_harness as h  # noqa: E402

def fds():
    out = {}
    for n in os.listdir("/proc/self/fd"):
        try:
            out[n] = os.readlink(f"/proc/self/fd/{n}")
        except OSError:
            pass
    return out

events = []
_orig_epoll = select.epoll
def TEpoll(*a, **k):
    events.append(("epoll", "".join(traceback.format_stack(limit=10))))
    return _orig_epoll(*a, **k)
select.epoll = TEpoll
_orig_pipe = os.pipe
def tpipe():
    events.append(("pipe", "".join(traceback.format_stack(limit=8))))
    return _orig_pipe()
os.pipe = tpipe

base = Path(tempfile.mkdtemp(prefix="fd_", dir=iw.PLATFORM / "test_tmp"))
w = iw.IntegrationWorld(base)
h.verify_snapshot(iw.PLATFORM / "snapshot")
h.activate_snapshot(iw.PLATFORM / "snapshot")
before = fds()
import importlib  # noqa: E402
importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
mid = fds()
print("after import:", sorted(set(mid.items()) - set(before.items())))
cfg = h.HarnessConfig(snapshot_dir=iw.PLATFORM / "snapshot", allowed_manifest_roots=(w.raw.root,), allowed_data_roots=(w.raw.data,),
                      allowed_grid_roots=(w.raw.grid,), output_root=w.base / "o", chunk_size=4096)
r, rc = h.run_block_diagnostic(cfg, w.raw.root, w.raw.protocol, w.raw.block, {}, w.base / "o" / "run")
after = fds()
print("after run:", sorted(set(after.items()) - set(mid.items())))
for kind, stack in events:
    print("=====", kind)
    print(stack)
