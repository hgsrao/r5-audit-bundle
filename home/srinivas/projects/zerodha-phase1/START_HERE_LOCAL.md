# Zerodha R5 — canonical Ubuntu workspace

Use `/home/srinivas/projects/zerodha-phase1` for ongoing work. It is on the Ubuntu NVMe drive, `/dev/nvme0n1p2` (the 1 TB drive).

## Latest checkpoint and stress milestone

The PAPER_APPLY baseline is now committed locally at `eb26df7f59a27da1f7f90f5ff1aa667a8545ab01`, annotated tag `r5-paper-apply-baseline-20260924`. The engine working tree is clean; no push was performed. Earlier references below to uncommitted PAPER_APPLY changes describe the pre-checkpoint snapshot.

The 48-symbol stress milestone passed: 800 real bars per symbol (35,472 replay events), plus a forced 48-candidate burst and selective ANSI-86 lockout/reset scenario. Results and replay commands: `local_workspace/stress_48/RESULTS.md`. Natural replay took 7m15s including data verification/loading; the fault scenario took 1m17s. Native automatic state integration and durable restart recovery remain next. There is no persistent admission queue in this engine.

## Current local stage — 2026-09-24

PAPER_APPLY is now implemented locally for offline external replay. These changes are uncommitted on top of `4963f14`; the old branch audit describes the earlier SHADOW-only checkpoint. Start with `outputs/R5-PAPER-APPLY-BASELINE.md` for the reconciled Claude findings, validation evidence and remaining milestones.

```bash
cd /home/srinivas/projects/zerodha-phase1
source /home/srinivas/.venvs/zerodha-phase1-r5/bin/activate
python scripts/run_r5_paper_replay.py --compare-shadow
```

This command uses verified real stock and NIFTY/VIX data, a fresh in-memory plant, and the offline paper broker. It does not resume a prior trading session.

## Original baseline

- Branch: `codex/r5-paper-apply-blocker-closure`
- Commit: `4963f14fb107adc21909ef8a386758e03c553c72`
- This is the selected R5 baseline, not a claim that every historical experiment is integrated.
- The original consolidation change was `revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json`: its `data_dir` points to the canonical local dataset.
- Source paths retain their established layout so imports, tests, and history remain valid.

## Where to work

| Path | Purpose |
|---|---|
| `revision5/` | Active R5 plant, protection, supervisory bridge, governor, and dynamic controls |
| `revision2_external/orchestrator.py` | External replay orchestrator used by the R5 ledger replay tests |
| `revision2/`, `revision2_external/`, `blocks/`, `runtime/` | Existing engine dependencies; use this checkout's versions |
| `tests/test_revision5_*.py`, `tests/test_r5_*.py` | Active R5 tests |
| `outputs/R5-ECS-GRID-DISPATCH-INTEGRATION-AUDIT.md` | R5 grid/dispatch audit; section 11 records blocker closure |
| `outputs/*dynamic-parameterization-audit.md` | Controller and black-box audit records |
| `data/frozen_48_1min_20230703_20260824/` | Canonical frozen dataset: 48 CSVs and 3 acquisition metadata files |
| `local_workspace/recovery/` | Preserved backup work, for review before integration |
| `local_workspace/records/` | Source paths, checksums, recovered-file inventory, and branch snapshots |
| `local_workspace/validation/` | Local consolidation validation records |

## Python environment

Use the existing Ubuntu environment; do not copy an old laptop virtual environment:

```bash
cd /home/srinivas/projects/zerodha-phase1
source /home/srinivas/.venvs/zerodha-phase1-r5/bin/activate
```

Run the two previously data-blocked offline replay checks:

```bash
python -m pytest -q \
  tests/test_revision5_plant_control.py::test_shadow_mode_leaves_the_replay_trade_ledger_unchanged \
  tests/test_r5_paper_apply_blocker_closure.py::test_attaching_a_real_plant_with_a_tripped_bay_still_leaves_the_shadow_ledger_unchanged
```

## Recovery policy and inventory

`backup_code_and_notes_20260923.zip` preserves 108 source/configuration/document files from the 12 known `ECS_Project*` backup directories whose bytes were absent from the current checkout and cached remote history. Original relative paths and SHA-256 checksums are in `records/recovered-files.json`. These are recovery candidates, not approved newer engine versions. The archive prevents old tests from being collected accidentally.

The extra R5 test is at archive member `ECS_Project_BB09_BB10/tests/test_r5_signal_to_paper_integration.py`. Review it before adding it to active `tests/`.

`backup_project_history.bundle` preserves the backup ECS_Project branch history, including two tips absent from this local repository: `feature/inhouse-sealed-validation-v3` at `16efdc4bbfa187b371f5e4297781458a86e002b1`, and `quarantine/mtf-extraction-0d713ac` at `5b4bf79ebbd73281210641668c18899d091664d9`. Their current GitHub presence was not established by this recovery. They were not merged into R5.

`historical_acquisition_reference.zip` preserves the historical dataset acquisition scripts and adjacent provenance records. These are references, not startup commands.

The recovery was scoped to known project source/test/configuration directories and relevant notes, excluding credentials, caches, environments, large generated outputs and unrelated backups. It is not a complete copy of the 500 GB backup drive. The original backup remains intact.

## Data integrity and local changes

All 48 CSVs matched the frozen manifest, and all 51 destination files matched their source bytes. Total: 816,644,109 bytes. Full local file hashes are in `local_workspace/records/dataset-checksums.json`.

The data directory, this guide, and `local_workspace/` are locally excluded using `.git/info/exclude`. They remain on this PC and are not in Git commits. No engine code was changed, branches merged, commits created, or trading enabled during consolidation.

## Consolidation validation — 2026-09-24

Both formerly data-blocked replay tests passed: **2 passed**, with 50 existing timedelta deprecation warnings, in 64.22 seconds. See `local_workspace/validation/consolidation-validation.txt`.

## Agent outputs

See `local_workspace/agent_outputs/README.md` for recovered Qwen reports, Claude review artifacts, integrated R5 audit records, source-hash checks, and task attribution.

Additional Claude laptop sessions and saved file versions: `/home/srinivas/projects/zerodha-phase1/local_workspace/agent_outputs/claude/laptop_sessions/README.md`.
