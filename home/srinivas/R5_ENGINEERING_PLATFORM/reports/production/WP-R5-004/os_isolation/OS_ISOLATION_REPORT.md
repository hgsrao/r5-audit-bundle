# WP-R5-004-OS-ISOLATION — implementation and OS test receipt

Classification: code implementation + synthetic OS tests. **No raw market data, no replay, no broker/live/models.**
No installs, no sudo. Protected snapshot and the original repo are unchanged (metadata fingerprints below).
The real-data gate **remains closed**.

## 1. What was built
| file (work/wp004_train_harness) | role |
|---|---|
| `harness/os_isolation.py` | plan builder, bwrap argv builder, independent argv auditor, launcher, host-side witness, live re-probe, release gate |
| `harness/os_isolation_bootstrap.py` | in-sandbox bootstrap: live verification, pin checks, then runs the target |
| `harness/wp004_train_harness.py` | `os_isolation_witness()` now verifies a live launched boundary **and** the closed release gate (only that function + one comment changed) |
| `harness/run_nonsealed_diagnostic.py` | docstring only |
| `harness_tests/test_os_isolation.py`, `os_probes/*`, `mutation_os_isolation.py`, `make_os_isolation_receipts.py`, `backup_fp.py`, `env_probe.py`, `os_isolation_backup_before.py` | tests, probes, mutation check, receipt tooling |

### Boundary (built from an EMPTY tmpfs root — the host root is never bound, not even read-only)
* Namespaces: user, pid, net, ipc, uts, cgroup; `--disable-userns`, `--cap-drop ALL`, `--new-session`, `--die-with-parent`,
  `--clearenv`, root remounted read-only. No network interface at all. Descendants inherit everything.
* Exposed, and nothing else (all verified inside the sandbox from `/proc/self/mountinfo`):
  * runtime: venv prefix + interpreter base prefix (same paths, ro), the individual shared-library **files** that `ldd` reports for
    the interpreter and its extension modules (12 files, listed in the JSON receipt; never a lib directory), the symlink chain of
    the venv interpreter (venv → uv alias dir → real dir) recreated as symlinks;
  * `/code/<name>`: audited code roots, ro, tree-sha256 pinned (harness dir; snapshot dir in one test);
  * `/in/<alias>`: approved standalone input artifacts as **file** binds, sha256 pinned; the parent directory is never mounted;
  * `/out`: the single writable bind (scoped output dir); `/scratch` (64 MiB tmpfs), `/tmp` (tmpfs), `/proc`, `/dev`.
* Not present in the child: `/home/srinivas` except `.venvs` and `.local` (runtime prefixes), original repos, projects, raw data
  roots, secrets, `/etc`, `/bin`, `/run`, validation/holdout material (never mounted; only explicit file binds exist).
* Fail-closed pre-launch checks (`BroadMountError`/`PinMismatch`/`UnsupportedEnvironment`): broad deny list (`/`, `/home`, home,
  `/usr`, `/etc`, …), `protected_paths` (secret/repo/raw trees: not bound, not contained, not exposed by an ancestor), `no_expose_paths`
  (project root etc.), input parent dirs, symlinked/unresolved roots, wrong code/input pin, setuid or too-old bwrap, missing tools.
  `audit_argv` parses the final argv independently (unknown option ⇒ refuse, required isolation flags, only `/out` writable).

### Witness (not a flag, not JSON)
1. `launch()` starts bwrap with `--info-fd`; bwrap's own namespace inodes are compared with the child's self-report and, when readable,
   with `/proc/<child-pid>/ns/*` and `/proc/<child-pid>/mountinfo` seen from the host; none may equal the launcher's namespaces.
2. The bootstrap announces READY, receives the host observation, and **re-probes the live kernel** (ns links, mount set + ro flags,
   root listing, fds, CapEff, NoNewPrivs, interfaces, pid) against it, then verifies code-tree and input pins **inside** the sandbox.
   Only then does the target run (`BOOTSTRAP_FAILED`, exit 97, otherwise).
3. `h.os_isolation_witness()` → `os_isolation.active_witness()` re-probes live on every call; a process not started by the bootstrap
   (host, fresh interpreter inside the sandbox, forged `_ACTIVE`, JSON file) is refused.
4. Even with a verified boundary, `os_isolation.require_real_run_release()` refuses: `REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None`.

## 2. Child status handling
`LaunchResult.status`: `OK`, `TARGET_FAILED` (rc via END marker), `TARGET_SIGNALED` (START seen, END missing; rc 137 for SIGKILL),
`BOOTSTRAP_FAILED` (rc 97 + reason), `SANDBOX_SETUP_FAILED` (bwrap error, no witness), `HOST_VERIFICATION_FAILED` (handshake never sent),
`TIMEOUT` (process group killed). `trusted_witness()` accepts only `OK`/`TARGET_FAILED`.

## 3. Commands and results (venv `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I`)
```
python -I -m pytest harness_tests/test_os_isolation.py -v -p no:cacheprovider      -> 41 passed   (TEST_LOG_os_isolation_pytest_v.txt / _junit.xml)
python -I -m pytest harness_tests/test_harness.py harness_tests/test_director_fixes.py -v -> 140 passed (TEST_LOG_old140_pytest_v.txt / _junit.xml)
python -I harness_tests/mutation_os_isolation.py                                    -> 10/10 mutants KILLED, no survivors (TEST_LOG_os_isolation_mutation_check.txt)
python -I harness_tests/make_os_isolation_receipts.py                               -> OS_ISOLATION_TEST_RECEIPT.json
```
The old `mutation_check.py` was **not** re-run to completion (an interrupted attempt left one mutant, `no_unplanned_open_guard`, in
`wp004_train_harness.py`; it was detected by diff against the preserved before-copy and restored; the file now differs from
`before/wp004_train_harness.py` only in the `os_isolation_witness` hunk and one comment).

### Test coverage (all against real bwrap launches, synthetic fixtures; canary/secret dir outside `/tmp`)
* allowed fixture reads via `builtins.open`, `os.open`, `mmap`, ctypes libc `open`, python subprocess;
* denied reads (canary, original repo file, `~/.bashrc`, `/etc/passwd`) via `builtins.open`, `os.open`, `mmap`, ctypes libc, raw
  `syscall(openat)`, python subprocess, `/bin/cat` subprocess, `fork` child, `../` escape, `/proc/self/root`, `/proc/1/root`;
* a host-side negative control proves the probe can read the canary / reach the listener when unsandboxed;
* network: TCP to a live host listener (never saw a connection), child-process TCP, host AF_UNIX socket, interfaces ⊆ {lo};
* writes: `/out` and `/scratch` allowed (output visible on host); `/code`, `/in`, `/etc`, `/` denied via builtins/os/subprocess; chroot,
  nested userns, mount denied; sources unchanged;
* tree walk of the child: no forbidden path component, `/in` = exactly the pinned files (sibling file in the same host dir absent),
  `/home` = `srinivas` → {`.venvs`,`.local`} only, fds at start = {0 /dev/null, 1, 2 pipes};
* mount plan: no `BROAD_DENY` source, directory binds == {runtime prefixes, code roots, out}; the auditor rejects `/`, `/home`, home,
  `/usr`, `/etc`, projects, project root, `work`, the original repo, secret parent as ro-bind, shared net, dropped isolation flags,
  `--dev-bind`, extra writable binds; `launch` refuses a broadened argv before bwrap starts; spec refuses broad output/code roots,
  symlinked output, directory or protected-tree inputs;
* wrong code/input pin (host pre-check) and in-sandbox pin failure with pre-check bypassed; forged ns ids / nonce / mount allowance /
  garbage / absent handshake ⇒ `BOOTSTRAP_FAILED`, target never runs; bwrap setup failure; missing bwrap; exit/raise/SIGKILL/timeout;
* harness gate: inside a verified sandbox the boundary is live-verified yet `os_isolation_witness()` still raises (release closed);
  fresh interpreter and forged expectation refused; host refuses; a forged witness JSON cannot open it;
* real `harness/` and `snapshot/` mounted ro and pin-verified in the sandbox, writes denied, snapshot tree hash unchanged;
* `strace -f` over the same audited argv: every in-sandbox `open*`/`connect` of host-secret paths returned -1, every connect failed.

## 4. Exact hashes
See `OS_ISOLATION_TEST_RECEIPT.json` (`source_sha256`, `harness_tree_sha256`, `snapshot_tree_sha256`, bwrap sha256 + 0.11.1,
strace 6.19, kernel 7.0.0-38) and `SHA256SUMS.txt`. Before copies: `before/` + `before/BEFORE_SHA256SUMS.txt`;
protected fingerprints: `PROTECTED_FINGERPRINT_BEFORE.json` vs `protected_unchanged` in the receipt (snapshot 562 files, original
repo 2660 files, `SNAPSHOT_MANIFEST.json` sha256 `0f5331a9…9ea0`: all identical, metadata-only comparison).

## 5. Limitations (read before relying on this)
* Threat model is *accidental or buggy native/Python access*, not a malicious target: the target runs in-process with the bootstrap,
  can read the nonce, and can print bogus markers. The kernel boundary, not the markers, is the guarantee.
* Shared kernel; no seccomp filter (ptrace/io_uring etc. are not additionally filtered). `--cap-drop ALL`, `--disable-userns`, no_new_privs only.
* Exposed by design: runtime prefixes (whole venv + interpreter dir, ro) and 12 system library files; ancestor directory *names* of
  those mounts (`/home/srinivas/.venvs`, `.local/share/uv/python`) are visible as empty parents.
* Host-side `/proc/<pid>` observation is best effort (recorded as `host_proc_view_available`); bwrap info-fd ids + the in-sandbox probe are mandatory.
* The input approval (`approval_id`) and "TRAIN-only" nature of an artifact are **recorded, not verified**: no code can prove content
  is TRAIN-only. sha256 only pins identity.
* TOCTOU: host pre-checks can race a swap; the in-sandbox sha256 re-check closes it for inputs and code (read after mount).
* Wrong-pin tests with host pre-check bypassed use a test-only parameter (`host_precheck=False`); `_tamper/_argv_hook/_prefix`
  are test-only hooks and cannot weaken the auditor.
* Sandbox cannot run packages whose shared libraries are outside the ldd closure (e.g. `_tkinter` is not importable).
  Full numpy/pandas import in the sandbox was **not** exercised (no replay was in scope).
* Not tested: user-namespace-disabled hosts (launch then reports `SANDBOX_SETUP_FAILED`, never a witness), memory/cpu limits, pid-limit.
* Old `mutation_check.py` not re-run (see §3).

## 6. Interval-plan compatibility (documented, NOT changed in code)
The current `WP004_REAL_EXECUTION_AUTHORIZATION_V1` describes **original raw files**: `canonical_path` under `data_root`/`grid_root`,
byte `intervals` into the raw file, `end` strictly below file size, `boundary_evidence.file_size_bytes_at_audit` = raw file size,
`terminal_boundary_row_authorized` (sentinel/cutoff row is read). Inside the sandbox the raw roots do not exist. A curated TRAIN-only
artifact is a **different object** (different path `/in/<alias>`, size, bytes, provenance). Minimal compatibility change for a *later*
package (not made here, so the fail-closed path is untouched): treat the artifact as the file in the plan — `roots.data_root/grid_root`
= the in-sandbox `/in` mount, `canonical_path=/in/<alias>`, `intervals` computed on the artifact, `boundary_evidence` issued for the
artifact (size at audit = artifact size, `evidence_artifact_sha256`), and a new `provenance_id` field value that names both the artifact
and the independent derivation from the raw source (the artifact's own provenance, distinct from the raw interval claim).
Open design point for the Director: `check_coverage` requires `intervals[-1].end < file size`, i.e. at least one byte (the terminal
boundary row) beyond the TRAIN range must exist in the file; a strictly TRAIN-only artifact that omits that row cannot satisfy it and
needs either the terminal row included (disclosed, never retained) or an explicit schema amendment. Neither is decided here.

## 7. Evidence required to enable the real-run release (none exists today)
1. Independently issued, hash-pinned TRAIN-only standalone input artifacts (stock + grid), derivation provenance distinct from raw files.
2. A Director release acceptance record, pinned by sha256 in `os_isolation.REAL_RUN_RELEASE_ACCEPTANCE_SHA256` (currently `None`),
   naming this isolation profile, the code-tree pins (harness, snapshot), the input pins and the execution package; plus the code that
   verifies it (`require_real_run_release` deliberately fails closed even if the constant were set).
3. An authorization JSON that describes the artifacts as mounted (§6), with its sha256 pinned externally.
4. A passing OS test receipt (this suite) for the exact launcher/bootstrap/harness hashes being released, re-run on the release host.
5. A real-run entry that is started *by* `os_isolation.launch` (target inside `/code/harness`), with `/in` holding only the approved artifacts.
