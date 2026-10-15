"""Mutation check: prove the synthetic tests have teeth (each mutant must make >=1 test fail). Restores the file always."""
import subprocess, sys, shutil
P = "/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/"
H = P + "harness/wp004_train_harness.py"
orig = open(H).read()
MUTANTS = {
    "no_chronology_check": ("if previous is not None and ts <= previous:", "if False:"),
    "no_consumed_hash": ("        self._digest.update(line)", "        pass"),
    "no_train_end_guard": ("            if day >= end_date:\n                raise ChronologyError(f\"{path.name}: row", "            if False:\n                raise ChronologyError(f\"{path.name}: row"),
    "no_size_check": ("if path.stat().st_size != record.size_bytes:", "if False:"),
    "no_strict_prefix": ("if strict_prefix and (self.reached_eof", "if False and (self.reached_eof"),
    "no_manifest_recompute": ("if recompute_manifest_hash(manifest) != pinned:", "if False:"),
    "tripwire_noop": ("            self._patch(owner, parts[-1], f\"{module_name}:{dotted}\")", "            pass"),
    "no_first_ts_check": ("if record is not None and first_raw != record.first_timestamp:", "if False:"),
}
results = {}
try:
    for name, (a, b) in MUTANTS.items():
        assert orig.count(a) >= 1, name
        open(H, "w").write(orig.replace(a, b, 1))
        r = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib",
                            "--basetemp=" + P + "test_tmp/mut_" + name, "-q", "--tb=no", "-x", "-W", "ignore::DeprecationWarning",
                            P + "harness_tests/test_harness.py"], capture_output=True, text=True,
                           env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
        results[name] = "KILLED" if r.returncode != 0 else "SURVIVED"
        results[name] += " | " + r.stdout.strip().splitlines()[-1]
finally:
    open(H, "w").write(orig)
for k, v in results.items():
    print(k, v)
