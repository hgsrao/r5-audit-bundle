# IMPLEMENTATION RECEIPT — WP-R5-004-TRAIN-HARNESS

Classification: NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC (mechanics only). Author: Claude (implementation only).
Status: **IMPLEMENTED + SYNTHETIC UNIT-VERIFIED. NOT execution-qualified. NOT production ready. NO replay performed.**
No actual48_certified, sealed-membership, parameter-authority, financial-performance or candidate claim is made. H/I/J unchanged (11/19/4).

## Unit verification vs actual replay
| | Done here | Not done |
|---|---|---|
| Unit verification on SYNTHETIC fixtures (generated, seeded pseudo-random OHLCV/grid) | yes — 51 tests | |
| Engine run through the direct factory on synthetic data | yes (mechanics only; 0 fills/trades) | |
| Any read/hash of real market data, real manifests of the dataset repo, real replay/backtest | | **none** |
| git invoked, original repos written, services/worker/Bridge/Dispatcher/config touched, commit/push, state/backlog writes | | **none** |

## Deliverables (all under allowed dirs)
Work dir `/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/`:
- `snapshot/` — supplied immutable snapshot, **unmodified** (562 files, re-hashed against `SNAPSHOT_MANIFEST.json` by every run; no extras, no `__pycache__`).
- `harness/wp004_train_harness.py` — harness (sha256 `55f15a09dcc94c143308c73f67090b725cb718ba1e4cb0f98ca7b7155e39e5f8`).
- `harness/run_nonsealed_diagnostic.py` — audited runner for the LATER package; refuses without authorization + all pins (sha256 `edb2ffa87b0d9919c534de2d5ec5e181353edb011b9777b730dbf96e2e6b716d`).
- `harness_tests/{synth.py,test_harness.py,mutation_check.py,make_receipts.py}` — synthetic fixtures, 51 tests, mutation check, receipt generator (the last two reference the original `tmp_probe/test_tmp` scratch paths, since deleted; re-point before reuse).

Reports dir `reports/production/WP-R5-004/train_harness/`: this file, `SNAPSHOT_SOURCE_MANIFEST.json`, `DEPENDENCY_HASH.json`, `DECLARED_UNQUALIFIED_INPUTS.json`, `EXECUTABLE_TEXT.md`, `TEST_LOG_pytest_v.txt`, `TEST_LOG_junit.xml`, `TEST_LOG_mutation_check.txt`, `SHA256SUMS.txt`. (`attempt1.*` files are from the earlier failed attempt, left untouched.)

## Identity
- HEAD `59371ff06d17b49d917a81aed294c2e254c97574`; protected indicator `revision2_external/indicators_talib.py` = `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (verified by file hash and by manifest; tampering test forges the manifest too and is still rejected).
- `SNAPSHOT_MANIFEST.json` sha256 `0f5331a9c253b5e95ecaa6d18837f93c252dd2b3502ac9ec6b8767dc960c9ea0`; tree digest `8f4c4800b7598d60d341793e407cc0180c5220ef3d8ef9b44b918b66f1fd675e`; protocol v2 file sha256 `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`.
- Imports proven: 58 snapshot sources loaded by factory/worker/orchestrator/plant/journal/dataset-manifest imports, all listed in the manifest; no module loaded from `/home/srinivas/projects/...` (`audit_loaded_modules`, with a negative control). Snapshot is first on `sys.path`; foreign pre-imports are refused. Environment hash in `DEPENDENCY_HASH.json` (python 3.12.14, existing venv, nothing installed).
- Snapshot engine code was **not modified**. Code-parent drift (protocol parent `c0b4672` vs HEAD `59371ff`) is *not* evaluated (needs git, forbidden) and is not accepted as sealed identity.

## Route implemented
`scripts/diagnostics/r5_block1_acceptance.py:execute_block(root, protocol, block, params, combined_cycle_state_path=None, output_path=<guarded>, fleet_loading_policy=None, feedback_compaction=False, prepare=<harness prepare>)`. No lifecycle TEST-ONLY seam, no identity guard bypassed. `assert_factory_contract` fails closed if the factory lacks any of those parameters. CNC runtime is None (`runtime_receipts.json` = `null`, no `combined_cycle_runtime` key). Params `{}` → registry defaults; no risk/strategy/calibration value touched.

## What the bounded `prepare` does (differences from `worker.prepare_block`)
- No `verify_manifest`, no `sha256_file`, no `MarketDataLoader`/`rglob`: stock files are located as `manifest.data_dir/record.filename` only after metadata checks.
- Stock/grid files are read through `BoundedLineReader`: unbuffered binary, fixed chunks, every physical byte counted, SHA-256 over **exactly the consumed lines** (warmup + target + one sentinel; grid prefix + the one cutoff-detecting row). Over-read is asserted `< chunk_size`, and `physical_bytes_read < size_bytes` (else `ReadBoundaryError`: bounded access not proven).
- `slice_sha256` now binds the consumed-prefix hashes (the original is count/timestamp-only and content-blind — demonstrated in a test).
- Rejections: unsafe/relative/`..`/symlinked roots and paths, data_dir/grid path outside declared roots, manifest hash pin mismatch/malformed, recomputed-record hash mismatch, symbol-count inconsistency, size mismatch, first-row ≠ manifest first_timestamp, consumed extent beyond manifest, rows at/after `train_end_exclusive` (incl. sentinel), non-increasing/duplicate timestamps (stock and grid), missing/out-of-order sentinel, missing/unexpected sessions, short warmup, shape errors (extra/short fields, quotes, lone CR, duplicate/missing columns), block ≠ protocol Stage B Block 1, protocol live_trading/broker_network_access ≠ false, grid sha/feeds mismatch.
- Preserved: original clock-escape and sentinel-in-clock checks, `prepare_market_data`, `build_clock`, `convert_stock_rows`, `exchange_ts`.

## Tests actually run (final: `51 passed`, ~25 s; also run repeatedly during development)
Command: `PYTHONDONTWRITEBYTECODE=1 /home/srinivas/.venvs/zerodha-phase1-r5/bin/python -m pytest -p no:cacheprovider --import-mode=importlib --basetemp=<work>/test_tmp -v -W ignore::DeprecationWarning harness_tests/test_harness.py` (full output in `TEST_LOG_pytest_v.txt`; the ignored DeprecationWarning is pandas `Timedelta(minutes=…)` in both the harness line and the original worker line).
- Frame-for-frame equality (`assert_frame_equal`, exact) of frames/feeds vs the snapshot's original `prepare_block` on synthetic data: LF, BOM+CRLF, `date`-column variants; common audit fields identical.
- Engine outputs (metrics, plant_control, governor_authority, micom, trades) identical to the snapshot's original `worker.execute_block` on synthetic blocks, including a 3-symbol run exercising governor ENTRY decisions (labels only; all values synthetic).
- Read boundary: positive (accounting == independent `open()` spy; consumed bytes == independently computed end of sentinel row; poison tail never physically read); poison-beyond-boundary changes nothing; negative controls (chunk > file ⇒ `ReadBoundaryError`; physical cap; oversize line).
- Hash spy: no `sha256_file`/`_sha256_file`/`verify_manifest` call; bytes hashed by the reader == total consumed bytes; no market-file-sized hash.
- Content change: same-size one-digit edit changes consumed hash and `slice_sha256` while the counts-only audit is identical; the other symbol is unaffected; grid-content edit likewise.
- Chronology/sentinel/error behaviour; wrong-manifest variants; unsafe roots; output guard; snapshot drift (modified/extra/missing/HEAD/pin/malformed/forged-protected-indicator) incl. e2e proof that no market file is opened when code drift or a bad output path is detected.
- Tripwire: each of 13 targets (kiteconnect client, Kite adapter init/get_gtts/ensure_cnc_gtt/convert_position/protection_tick_size, InstrumentMetadataSnapshot build/tick_size, CombinedCycleStore/Runtime, HandoffManager, EngineBController, `build_paper_combined_cycle_runtime`) fires when called (negative control) and is restored afterwards; sockets, raw `open`/`Path.read_bytes`/`pd.read_csv` on data roots and writes outside the output root fire. In the two end-to-end synthetic runs all counters are zero (`tripwire.counts == {}`), engine accounting reconciles, and synthetic inputs + snapshot are byte-identical afterwards.
- Mutation check (`TEST_LOG_mutation_check.txt`): 8 deliberate harness defects (chronology, consumed hash, train-end guard, size check, strict prefix, manifest recompute, tripwire, first-timestamp check) — all 8 caught.

## Missing evidence / known limits (not hidden)
1. **No real data was touched**, so real manifests, `data_dir`, grid manifest, file layouts, timestamp formats and sizes are unaudited. Synthetic sessions have 40–120 bars (not 375), 2–3 symbols, zero fills/trades; exit, plant-economics and trade paths are therefore not exercised.
2. Stock files are read **from file start** through the sentinel (needed for the 60-bar warmup and the prefix hash). For real data this includes bytes dated before `train_start` (file begins 2023-07-03) and months of prefix per symbol. No offset index exists without reading; Director must accept this or supply a boundary-audited alternative.
3. Grid: one boundary row per feed is read, parsed and discarded to detect the cutoff (protocol text says rows after block end are not parsed). Reported as `boundary_rows_parsed_and_discarded`; it is inside the consumed hash. Needs Director ruling.
4. Whole-file manifest sha256/row_count cannot be verified without whole-file hashing (forbidden); a same-size edit inside the prefix passes metadata checks and is visible only in the recorded consumed hash (test documents this). Size/first-timestamp checks fail closed: if the newly acquired data legitimately differs from the historical manifest, replay is blocked until the Director rules.
5. Tripwire/open-spy are in-process Python patches (`builtins.open`/`io.open`, sockets, listed classes). They do not see `os.open`, `mmap` or native-library reads or other processes; there is no strace/OS-level witness. Physical-byte accounting is the harness reader's own, cross-checked only against an in-test open() spy.
6. The Kite module is imported (import-only, by `broker_adapter_kite` / orchestrator); `KiteConnect.__init__` is tripwired and never called.
7. `grid-manifest-local.json` is not in the snapshot; the later package must supply a root holding it (single `root` argument covers both manifests). The grid manifest's `path` entries must lie under the declared grid root.
8. Recorded-not-changed: existing kill-switch/drawdown/daily/position behaviour and inactive weekly/2%-daily governors (see `DECLARED_UNQUALIFIED_INPUTS.json`). `runtime_safety_contract.json` is emitted at execution time.
9. Independent review not performed. No commit, no state/backlog write, no dispatcher interaction.

## Remaining real-data gates (for the separate sequential execution package)
Director rulings on items 2–4 above; audit of roots, manifest `data_dir`, grid manifest/paths, ordering and physical boundary assumptions; params file and its hash pin; authorization receipt; independent review of this package; then single-instance sequential execution, followed by comparison of `physical_bytes_read < size_bytes`, consumed hashes, tripwire counts and snapshot re-verification in `harness_receipt.json`.
