"""Smoke driver: build the synthetic integration world and launch the curated target inside real bwrap. Synthetic only."""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/harness_tests")
import integration_world as iw  # noqa: E402
import curated_launcher as cl  # noqa: E402

base = Path(iw.PLATFORM / "test_tmp" / "smoke")
shutil.rmtree(base, ignore_errors=True)
w = iw.IntegrationWorld(base, pretrain_variant="--pretrain" in sys.argv)
t = time.time()
run = cl.run_curated(w.cfg())
print(run.result.status, run.result.returncode, run.result.detail, round(time.time() - t, 1), "s")
print(run.result.stdout[-1500:])
print(run.result.stderr[-4000:])
