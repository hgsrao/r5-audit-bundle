"""One-off: preserve pre-OS-isolation versions + hashes as 'before' copies (never overwrites) and record protected-tree
fingerprints (metadata only; no data file is opened)."""
import hashlib
import json
import os
import shutil
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
R = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004")
B = R / "os_isolation" / "before"
B.mkdir(parents=True, exist_ok=True)
srcs = [*sorted((P / "harness").glob("*.py")), *sorted((P / "harness_tests").glob("*.py")),
        *(R / "train_harness" / n for n in ("REQUIRED_EXTERNAL_INPUT_SCHEMA.md", "IMPLEMENTATION_RECEIPT.md", "SHA256SUMS.txt"))]
lines = []
for s in srcs:
    if s.name.startswith(("os_isolation_backup", "env_probe")):
        continue
    d = B / s.name
    if not d.exists():
        shutil.copy2(s, d)
    lines.append(f"{hashlib.sha256(d.read_bytes()).hexdigest()}  {d.name}")
(B / "BEFORE_SHA256SUMS.txt").write_text("\n".join(lines) + "\n")


def meta_fingerprint(root):
    h, n = hashlib.sha256(), 0
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            st = os.lstat(p)
            h.update(f"{os.path.relpath(p, root)}|{st.st_size}|{st.st_mtime_ns}|{st.st_mode}\n".encode())
            n += 1
    return dict(files=n, metadata_sha256=h.hexdigest())


fp = dict(snapshot=meta_fingerprint(P / "snapshot"),
          original_repo=meta_fingerprint("/home/srinivas/projects/zerodha-r5-governor-refactor"),
          snapshot_manifest_sha256=hashlib.sha256((P / "SNAPSHOT_MANIFEST.json").read_bytes()).hexdigest())
(B.parent / "PROTECTED_FINGERPRINT_BEFORE.json").write_text(json.dumps(fp, indent=2, sort_keys=True) + "\n")
print("\n".join(lines))
print(json.dumps(fp, indent=2))
