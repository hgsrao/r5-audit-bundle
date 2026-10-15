"""Sandbox-side child-status probe. argv[1] in {ok, fail:N, kill, raise, hang}."""
import os
import signal
import sys
import time

mode = sys.argv[1]
if mode == "ok":
    print("done")
elif mode.startswith("fail:"):
    sys.exit(int(mode.split(":")[1]))
elif mode == "kill":
    os.kill(os.getpid(), signal.SIGKILL)
elif mode == "raise":
    raise RuntimeError("boom")
elif mode == "hang":
    time.sleep(600)
