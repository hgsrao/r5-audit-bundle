# WP-R5-004 — GIT_IDENTITY_REPORT (report-only, 2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


I cannot run git or `sha256sum` in this session (Read/Glob/Grep only). **Nothing below was re-verified by me today.** Sources: `evidence/git_identity_raw.txt` (operator-captured 2026-10-07T07:34:41Z) and the identity given in the resume order [OPERATOR]. INTERIM_FINDINGS.md says the worker re-ran git on 2026-10-07 and matched the raw file; that is [CARRIED].

## 1. Frozen identity

| Item | Value | Source |
|---|---|---|
| Repo | `/home/srinivas/projects/zerodha-r5-governor-refactor` (read-only) | task |
| Branch | `feature/ir02a-parameter-closure` | raw:4 |
| HEAD | `59371ff06d17b49d917a81aed294c2e254c97574` ("R5 IR-02A: ORC-13 regime trace, derived warm-up/history, allocator and ATR fail-closed (parameter authority NOT yet closed)") | raw:3-5 |
| Working tree | **DIRTY**: 8 tracked files modified (+135/−90), 239 untracked | raw:7-14, :43-52, :80-81 |
| Protected indicator SHA | `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` | section 3 |

## 2. Modified tracked files (8)

| File | Working-tree sha256 | HEAD blob sha256 | On replay path? |
|---|---|---|---|
| revision2_external/indicators_talib.py | 5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618 | a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2 | **YES** (`orchestrator.py:56`) |
| revision2_external/grid_context.py | 903ea27aeb669f99008d64b17c3df3b65f8ef7ae0d3fd67c72210bf21e330931 | 3f97032bf2bf8f5b4b3edf62a6e33600d0c7d6ca798f5cfaf55fb1172b8301a6 | **YES** (`orchestrator.py:55`, `:2357`) |
| docs/r5_remediation_project/EXECUTION_REPORT.md | 11710bff55b005d82960c86d26f4302c6659df6084e522816028b5246f5f66a9 | 4251764aa389076c2afa5730c4ba693f8ab74eca31bb6f00253dd2161b0fd061 | no |
| scripts/diagnostics/data/pa_symmetry_indicators_talib.patch | a0b6d5ff2ebff15059cfa24726b2735494ee44cb942c096bef4e754b9b2b7089 | bbae6224edcc5d04a59d2ba5266e7718eda91b23a4595644a14274590f6d8e1b | no (used only by the isolation arm worker; CARRIED) |
| tests/test_block1_isolation_harness.py | bd14f5f15235374e038f6db665c1521302aab90dd75eea56f987648cc3481d58 | bc0e3ffc02fcce2fc0cfef0d4c35ca30bd52b33c13252f67998f7d0f2a45645b | no (test) |
| tests/test_revision5_bb04_dynamic_parameterization.py | 6914f910f73ece1377ade4d45f5c6e0926ad3fe8d77acc0f31fb7fc92ba4144b | fae98939eb92c91551ad403a7338938dcfd1de4fa07e9ed805f378a2f766983a | no (test) |
| tests/test_revision5_engine_applicability.py | d35289fbe189ffbd2db9f52781e70809d76cd960582a8d0d3de7db5c0cac9129 | e784297028f979ba79d5fb8e1c6ff8dbb4fd5a907b3a481f2d4ff3905f727f74 | no (test) |
| tests_external/test_grid_context.py | f858db51621a83e911617d086a97e05978384ca12ac3a16796fc855264d81aba | d6fe4e3f443b37cf246169558691bfd38330492f50b836a34b32252160956587 | no (test) |

Hashes from raw:62-79.

## 3. The indicator file — what is established and what is not

- **Operator-verified [OPERATOR]:** the HEAD indicator blob, the preserved protected 59371ff indicator, and the isolated NODE-001 campaign checkout all have SHA256 `a011b295…883b2`. The original working-tree file is `5ba12643…c439bc618`. The existing initial user protection directive is `a011b295`.
- **Receipts on file [FRESH]:** `campaign/WORK_PACKAGES.json:6` (`protected_sha256`), `wp01/checkpoint_receipt.json:5-8` (maps both 1b49e29 and 59371ff to `a011b295…`, and `protected_worktree_sha256`), and `wp02/capacity_receipt.json:2` all record `a011b295…`. A grep of NODE-001 md/json/txt files found **no** document that mentions `5ba12643`.
- **Implication.** The working-tree file is NOT the protected file. The working tree has diverged from the protected SHA, and no ratification of the changed file has occurred. This supersedes the original order's premise that 5ba12643 is the protected research file.
- **What the diff does [FRESH, partial].** It adds overridable hooks `_combine_raw_signal` and `_quality_band_confidence` (`indicators_talib.py:286-313`); `evaluate()` calls them (`:417`, `:434`). The comment at `:282-284` claims the default bodies equal the original expressions with identical operand order. **I could not compare with HEAD (no git).** Behaviour neutrality is UNPROVEN (author claim only). The diff is 58 lines (raw:46), more than these two hooks obviously account for; the remainder is unexamined, so UNKNOWN.
- **grid_context.py [FRESH].** A new fail-closed branch returns `SYMBOL_GRID_PHASE_UNAVAILABLE` when `delta_phi` is not finite (`:216-219`). That changes the recorded shadow observation whenever TA-Lib yields NaN. `observe()` output goes to `grid_shadow_observations` (`orchestrator.py:2357-2364`) and the report (`:3014-3018`). Whether any trading decision consumes it was not traced. **Effect on trades: UNKNOWN. Effect on the report: certain when NaN occurs.** The c05 baseline recorded `grid_context.py` as `3f97032b…`, the HEAD blob (`run_manifest.json:59`), so c05 results predate this change.

## 4. Untracked files (239; raw:80-81)

Per-directory counts inside collapsed directories are UNKNOWN from `--porcelain` (raw:15-42). The total of 239 is [CARRIED] from the INTERIM `--untracked-files=all` recount.

| Group | Examples | On the import path? |
|---|---|---|
| Root-level scripts (3) | `build_isolated_d02_candidate.py`, `manual_diff_audit.py`, `run_commit_readiness_audit.py` | No import found [CARRIED]. They enter the runner's aggregate source hash, which includes root-level `.py` (`run_r5_paper_lifecycle.py:160-166`). |
| `outputs/**` (D02 audit docs, commit-candidate patch, manifests, c04/c05 run dirs, diagnostics) | raw:18-31 | No. Excluded from the aggregate hash (`SOURCE_EXCLUDED_DIRS`, `:57-60`). |
| `scripts/research/` | `r5_pa_gate_arms.py` | Not imported by the engine [CARRIED grep]. `scripts` is in `SOURCE_EXTRA_DIRS`, so it **is** in the aggregate hash. |
| New tests (5 in `tests/`, 4 in `tests_external/`) | raw:34-42 | No. Excluded directories. |

## 5. Judgement: is execution qualification VALID for the current state?

**NO. Execution qualification is NOT VALID for the current working tree.**
1. Two files on the replay path differ from HEAD. One of them, `indicators_talib.py`, also differs from the protected SHA, and that difference is unratified.
2. Behaviour neutrality of that diff is unproven, and the grid_context diff changes outputs when NaN occurs.
3. **Pin gap [FRESH].** WP-R5-003's replay-path table does not list `indicators_talib.py` or `grid_context.py`. WP-R5-002's table (INPUT_INTEGRITY_REPORT §4) lists `grid_context.py` at 903ea27a…, which is already the modified working-tree value, but not `indicators_talib.py`. So "hashes unchanged since WP-R5-002" (WP-R5-003 §1.3) never covered the protected file.
4. **Provenance defect [FRESH].** The `revision5/risk_governance.py` hash recorded in EXECUTION_PROVENANCE.md (`cc9d33ab…3b5a`) is 73 hex characters, so it is not a valid sha256, and its tail repeats the orchestrator hash. It cannot serve as an identity pin.
5. **Historical results do not transfer [FRESH].** The c05 baseline ran at HEAD `411712af…` with 808 status entries (`run_manifest.json:667-668`, `:1479`). Its `indicators_talib.py` was `70ff1999…` (`:410`), its orchestrator `7a0e7ad7…` (`:64`) and its transaction_costs `2043c8c1…` (`:54`). All three differ from the files named today. `orchestrator.py` (6885bc41…) and `transaction_costs.py` (7a570e10…) are not in the modified list, so they changed through commits after 411712af.

The identity **record** here is complete (HEAD, branch, dirty set, hashes). The identity is **not qualified**.

## 6. Recommended way to pin identity (nothing committed by me)

The operator picks one:
- **(a) Revert for the run.** Use a scratch export with `indicators_talib.py` and `grid_context.py` at HEAD, leaving the original working tree untouched. Then the protected `a011b295` is the replay file. The operator must decide how the hook changes and the NaN branch are preserved elsewhere.
- **(b) Ratify** the changed files explicitly: an operator statement naming `5ba12643…` and `903ea27a…`, with a diff review recorded in a receipt. Only the operator can do this.
- **(c) Commit** the intended state as an operator-made commit, then pin that commit.

In every case take a **file-hash manifest** of the whole replay path at run time. The lifecycle runner already produces one: an aggregate sha256 over every engine `.py`, tracked or not, plus HEAD and dirty status (`run_r5_paper_lifecycle.py:181-207`), and it aborts on mid-run drift (`:210-217`). The manifest must include `indicators_talib.py`, `grid_context.py` and a **valid** `risk_governance.py` hash.

Nothing was committed, reverted or edited. Production NOT READY.