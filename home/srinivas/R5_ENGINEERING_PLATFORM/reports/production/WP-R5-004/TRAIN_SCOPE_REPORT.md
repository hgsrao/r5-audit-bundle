# WP-R5-004 — TRAIN_SCOPE_REPORT (report-only, 2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


Problem (WP-R5-003 Gate 0(a)): the existing code reads only block rows but hashes WHOLE files. Each frozen stock file spans 2023-07-03..2026-08-24, so hashing reads Validation and Holdout bytes. Static evidence only; no data file was opened or hashed. Tags as in REPLAY_ENTRYPOINT.md.

## 1. Facts re-verified today [FRESH]

- `prepare_block` (`scripts/run_r5_step5_candidate.py:419-581`) does five things in order:
  1. It loads the manifest and requires `manifest_hash` to equal the protocol value (`:446-452`).
  2. It calls `verify_manifest(manifest)` (`:454`), which per WP-R5-003 hashes each whole file (`revision2/dataset_manifest.py:126-131`).
  3. It streams each stock CSV through `load_stock_block` until the first sentinel row after the block (`:490`, `:231-236`).
  4. It certifies the data and builds the clock.
  5. It calls `load_grid_prefix` (`:560`), which hashes the whole grid file at `:331-336` against the protocol seal, then breaks at the first row past the cutoff (`:371-372`).
- `slice_sha256` is `canonical_json_hash` over per-symbol audit dicts (row counts, first/last timestamps, session counts, sentinel timestamp) plus the grid audit (`:257-277`, `:566-579`). **It contains no price or volume content.** This corrects the INTERIM acceptance check, which proposed `slice_sha256` equality alone. That check would not detect a difference in price values.
- Block 1 (Stage B) is 2023-12-05..2023-12-11, so its sentinel is the next session. All protocol blocks end by 2025-03-26 (WP-R5-002 PRO-01) [CARRIED], months before TRAIN ends.
- The c05 baseline manifest records `slice_sha256 d09e340b…4aae` for the historical Block 1 run (`run_manifest.json:318`). That run passed whole-file verification at the time.

## 2. OPTION A — authorised TRAIN-only frozen slice with recorded hashes

- **What is read (Codex correction).** An extractor may cut and hash chronological TRAIN prefixes without reading Validation/Holdout bytes, provided ordering and physical read boundaries are proved. Recomputing whole-file seals would read those bytes and is not authorized here.
- **Who.** Only the operator, or a party the operator authorises in writing. Not this worker (forbidden). The read must be logged against the SEALED_DATA_EXPOSURE_RECEIPT, because a prior exposure is already disclosed.
- **What is created.** TRAIN slices for the 48 stock files and required grid feeds, a cutting-procedure record and a content-hash list. The exact output count depends on the approved feed layout.
- **Hash provenance.** Slice hashes would be new facts with no independent prior record. They tie to the whole-file hashes only through the operator's procedure.
- **Effect on manifest verification (a defect).** A slice has a different size and sha256 from its manifest record, so `verify_manifest` fails. A new manifest changes `manifest_hash`, so the `:446-452` protocol check fails. The grid slice differs from the protocol seal, so `:331-336` fails. **Option A cannot pass the existing sealed checks and still needs a substitute loader or edited checks.** The extractor and sealed-check contract still require an approved design; a holdout read is not intrinsic to slicing.
- **Effect on `verify_engine_identity`.** None directly. In-repo loader edits would add to the ENGINE_PARENT_DRIFT list, which already fails on this tree.
- **Blast radius.** Medium: a new data lineage outside the sealed hashes.
- **Auditability.** Medium: it rests on a manual cutting step.
- **Reversibility.** Generated slices are reversible. Any separately authorized full-seal read would be irreversible exposure; none is authorized here.
- **Risk to sealed receipts.** The receipts remain untouched; a second hash lineage requires documented provenance. Exposure depends on the actual read procedure.

## 3. OPTION B — modify the qualification loader so manifest verification never needs Validation/Holdout data

The R5 repo is read-only here, so Option B is realised as an **out-of-repo substitute loader harness** injected through an existing seam: `run_lifecycle(..., _test_loader_substitute=...)` (`run_r5_paper_lifecycle.py:616-617`, `:693`), or equivalently `execute_block(..., prepare=...)` (`r5_block1_acceptance.py:114`). It is not a literal edit of `prepare_block`.

- **What is read.** For each of the 48 stock files, only the header through the warm-up and target rows to the sentinel row. For each grid feed, only the prefix to the cutoff. Python's buffered reader may over-read up to one buffer past the sentinel. The sentinel is months before 2025-07-01, so the over-read stays inside TRAIN. The harness must record `bytes_read` per file to show this.
- **What is created.** Harness code and tests under the platform tree (outside R5), a prefix-hash record per file (sha256 of bytes from offset 0 through the sentinel row's end, computed in the same streaming pass), a pin manifest, and run outputs under `runs/`.
- **Who is authorised.** The operator must (i) authorise the harness package, (ii) ratify the TEST-ONLY seam for a diagnostic run, and (iii) state that WP-R5-002's whole-file hashes (48/48 equal to both manifests) stand in for the seal check.
- **Hash provenance.** Whole-file integrity is NOT re-proved. It rests on WP-R5-002's recorded hashes, the `manifest_hash` check (metadata only) and a `stat` size check. The prefix hash is trust-on-first-use; its link to the whole-file hash cannot be shown without reading the rest of the file. **Stated weakness.** Partial mitigation: compare the prefix-derived audit (timestamps, counts, sentinel) with the historical c05 Block 1 audit. That is a consistency check, not a content proof (section 1).
- **Effect on manifest verification.** The harness checks `manifest_hash` against the protocol (no data bytes) and skips per-file hashing. It records that per-file hashing was deliberately replaced.
- **Effect on `verify_engine_identity`.** None while the harness lives outside the repo. The lifecycle runner tolerates ENGINE_PARENT_DRIFT by design (`:419-425`).
- **Blast radius.** Low. No repo, sealed-receipt or data change.
- **Auditability.** High: the harness is hashable and emits bytes-read counters and prefix hashes.
- **Reversibility.** Full. Delete the harness; nothing sealed changes.
- **Risk to sealed receipts.** None; nothing sealed is written or re-hashed.
- **Risks.** (1) The seam is labelled TEST ONLY and the resulting manifest is flagged as a test-substitute run. (2) The harness must be shown equivalent to `prepare_block` on its row logic (check 1 below).

## 4. RECOMMENDATION: Option B (out-of-repo substitute loader harness)

1. Option A cannot satisfy the existing sealed checks unchanged. Its cost relative to Option B has not been established.
2. Option B needs no Validation/Holdout read by anyone.
3. It leaves sealed receipts and the R5 repo untouched and is fully reversible.

This is a recommendation only. It is not authorised and nothing was implemented. Neither option is needed to qualify the execution path at this stage. **Implementation package needed:** WP-R5-005 (prepared, not submitted).

## 5. Exact acceptance checks for Option B

1. **Equivalence on synthetic fixtures.** The fixtures are synthetic CSVs generated inside the test, not market data. For the same synthetic manifest, the substitute loader and the original `prepare_block` must return DataFrames equal frame-for-frame (full content, not just `slice_sha256`), equal `slice_sha256`, equal grid feeds and equal `max_target_utc`.
2. **Counting spy.** On a synthetic file that continues past the sentinel into a Validation-dated region, the harness reads at most the sentinel row plus one buffer. Recorded `bytes_read` is below the file size, and no whole-file hash function is called.
3. **Negative control.** The original `prepare_block` on the same synthetic data does call whole-file hashing, which shows the spy works.
4. **Gate checks preserved.** A wrong `manifest_hash`, a missing sentinel, a sentinel not after the target, and a clock escape each raise the same error class as the original.
5. **Pin manifest.** It records sha256 of the harness, runner, factory, worker and all replay-path files, plus git HEAD and status (taken by an authorised party).
6. **No writes** into the R5 repo, the data roots or the baseline, shown by a before/after listing of the repo status.
7. **A real-data run only after the operator** ratifies the entry point and the identity decision. Output goes to `runs/` only.

Nothing here was run. Production NOT READY.