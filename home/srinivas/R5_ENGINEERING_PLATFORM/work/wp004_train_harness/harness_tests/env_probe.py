"""Host environment probe for the OS-isolation package (prints tool versions and the interpreter symlink chain; reads no data)."""
import os
import subprocess
import sys

for cmd in (["/usr/bin/bwrap", "--version"], ["/usr/bin/strace", "-V"]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(cmd[0], r.returncode, (r.stdout + r.stderr).strip().splitlines()[:1])
print("prefix", sys.prefix, "base_prefix", sys.base_prefix, "executable", sys.executable)
p = sys.executable
for _ in range(10):
    if not os.path.islink(p):
        break
    t = os.readlink(p)
    print("link", p, "->", t)
    p = t if os.path.isabs(t) else os.path.join(os.path.dirname(p), t)
print("realpath", os.path.realpath(sys.executable), "base realpath", os.path.realpath(sys.base_prefix))
print(open(sys.prefix + "/pyvenv.cfg").read())
