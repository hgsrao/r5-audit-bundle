"""One-off: preserve pre-integration versions + hashes as 'before' copies (never overwrites) and record the protected-tree
metadata fingerprints (no data file is opened)."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integration_fp  # noqa: E402

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
B = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004/isolated_integration")
(B / "before").mkdir(parents=True, exist_ok=True)
lines = []
for s in [*sorted((P / "harness").glob("*.py")), *sorted((P / "harness_tests").glob("test_*.py")), P / "harness_tests/synth.py"]:
    d = B / "before" / s.name
    if not d.exists():
        shutil.copy2(s, d)
    lines.append(f"{hashlib.sha256(d.read_bytes()).hexdigest()}  {d.name}")
(B / "before" / "BEFORE_SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
fp = dict(snapshot=integration_fp.meta(P / "snapshot"),
          original_repo=integration_fp.meta("/home/srinivas/projects/zerodha-r5-governor-refactor"),
          snapshot_manifest_sha256=hashlib.sha256((P / "SNAPSHOT_MANIFEST.json").read_bytes()).hexdigest())
if not (B / "PROTECTED_FINGERPRINT_BEFORE.json").exists():
    (B / "PROTECTED_FINGERPRINT_BEFORE.json").write_text(json.dumps(fp, indent=2, sort_keys=True) + "\n")
print("\n".join(lines))
print(json.dumps(fp, indent=2))
