"""One-off: preserve current versions + receipt hashes as historical 'before' copies (idempotent; never overwrites)."""
import hashlib
import shutil
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
R = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004/train_harness")
B = R / "before_director_fix"
B.mkdir(exist_ok=True)
srcs = [*sorted((P / "harness").glob("*.py")), *sorted((P / "harness_tests").glob("*.py")),
        *(R / n for n in ("IMPLEMENTATION_RECEIPT.md", "SHA256SUMS.txt", "TEST_LOG_junit.xml",
                          "TEST_LOG_mutation_check.txt", "TEST_LOG_pytest_v.txt", "EXECUTABLE_TEXT.md"))]
lines = []
for s in srcs:
    if s.name == "backup_before.py":
        continue
    d = B / s.name
    if not d.exists():
        shutil.copy2(s, d)
    lines.append(f"{hashlib.sha256(d.read_bytes()).hexdigest()}  {d.name}")
(B / "BEFORE_SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
