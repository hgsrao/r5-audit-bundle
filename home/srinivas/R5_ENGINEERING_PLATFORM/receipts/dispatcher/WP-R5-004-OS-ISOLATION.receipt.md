# Receipt WP-R5-004-OS-ISOLATION

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T12:04:57.110795+00:00 |
| finished_at | 2026-10-08T12:39:41.998649+00:00 |
| elapsed_seconds | 2084.885827225 |
| package_sha256 | bd745f33d63378230376297bae418e274da79fc3fecea62d062489e73230d887 |
| output_sha256 | ac2d0b329385b36e49e03ef6c57713c998853e669d09c3fa4a325975afe41dbc |
| response_file | WP-R5-004-OS-ISOLATION.response.txt |

## Objective
Implement and verify OS isolation with synthetic fixtures; preserve fail-closed real-data release

## Response
```text
OS isolation is implemented and tested with real `bwrap` launches against synthetic fixtures. The real-data gate is still closed.

**Test results** (venv python, `-I`):
- The new suite passed all 41 tests.
- The existing 140 tests still pass.
- A mutation check on the launcher killed 10 of 10 mutants.

I did not re-run the old `mutation_check.py` to completion. An interrupted attempt left one mutant in `wp004_train_harness.py` (`and False` in the unplanned-open guard). I caught it by diffing against the preserved before-copy and restored it. The file now differs from the before-copy only in the `os_isolation_witness` hunk and one comment.

**What the launcher does:**
- **Mounts:** the child root is an empty tmpfs; the host root is never bound, not even read-only. It gets the venv and interpreter prefixes, 12 individual library files, the pinned code roots and the pinned input files as file binds. The only writable mounts are `/out`, `/scratch` and `/tmp`.
- **Isolation:** user, pid, net, ipc, uts and cgroup namespaces are unshared, nested user namespaces are disabled, all capabilities are dropped, and only stdio fds are inherited.
- **Witness:** it comes from `bwrap`'s own namespace report, the host's view of `/proc/<pid>`, and a live re-probe inside the sandbox. A flag, JSON file, fresh interpreter or forged state does not open it.
- **Release gate:** `os_isolation_witness()` verifies the live boundary, then refuses anyway because the release gate is closed (`REAL_RUN_RELEASE_ACCEPTANCE_SHA256` is `None`).

**What the tests showed:**
- **Allowed reads:** the fixture read works through `builtins.open`, `os.open`, `mmap`, ctypes, subprocess, `fork` and a `/bin/cat` subprocess.
- **Denied reads:** the canary, an original-repo file and `~/.bashrc` were denied through all of those plus `../`, `/proc/self/root`, raw `openat` and `/proc/1/root`. A negative control confirms the probe reads the canary when unsandboxed.
- **Network:** TCP to a live host listener, a child-pro
... (truncated; see the response file)
```
