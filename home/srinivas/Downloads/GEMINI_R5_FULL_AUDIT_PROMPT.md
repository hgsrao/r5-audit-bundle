Perform a complete provenance and implementation audit of the Zerodha trading-system work copied onto this computer’s hard disk.

Do not modify files, branches, datasets, reports, protocols, or GitHub. This is a read-only audit. Do not begin implementation or calibration.

The audit must cover every available project folder, branch, worktree, archive, and revision from Revision 0 through Revision 5, not only Engine C.

At minimum inspect:

- `~/projects/`
- `~/R5_ENGINEERING_PLATFORM/`
- every Zerodha repository and worktree;
- all local Git branches and reflogs;
- all GitHub-tracked branches available locally;
- archived Claude/Codex worktrees;
- `zerodha-phase1`;
- `zerodha-engine-c`;
- `zerodha-r5-governor-refactor`;
- `r5_c04b_candidate`;
- `zerodha-r5-trace`;
- all `zerodha-claude-*` copies;
- all calibration and research folders;
- all `revision0/`, `revision1/`, `revision2/`, `revision3/`, `revision4/`, and `revision5/` directories.

## Primary objective

Determine exactly what has already been implemented anywhere in the historical system and what can be reused in the current Engine C / Revision 5 branch.

Do not assume that the current Engine C folder is the complete system. Search all revisions for earlier implementations of:

- PID controllers;
- parameter registries;
- dynamic parameter systems;
- governor controllers;
- AVR controllers;
- dispatch controllers;
- HRSG controls;
- plant protection;
- Mark V;
- MiCOM/SEL protection;
- studies weighting;
- Box 6 entry/exit control;
- closed-loop control;
- calibration tools;
- sensitivity tests;
- protocol sealing;
- cross-engine validation;
- long-holding and multi-session logic.

## Compare against the existing Claude implementation programme

Read and audit the complete implementation programme supplied to Claude, including Phases 0–11 and the `final_exit_authority` carry-over.

For every phase and work item, classify it as:

1. Already complete in current Engine C.
2. Complete in an older revision and reusable.
3. Partially complete and portable.
4. Implemented but not wired into current Engine C.
5. Implemented but inactive, shadow-only, or advisory.
6. Implemented but not parameterized.
7. Implemented but not tested end-to-end.
8. Missing everywhere.
9. Contradicted by newer code.
10. Obsolete and should not be ported.

Do not recommend redoing work that already exists. Identify the exact source revision, branch, commit, file, and line where the reusable implementation lives.

## Full controller and parameter audit

Inventory every PID and PID-like controller across Revisions 0–5.

For each controller record:

- revision;
- repository/path;
- branch;
- commit;
- file and line;
- class/function;
- inputs;
- setpoint;
- error formula;
- Kp/Ki/Kd or equivalent;
- integral behavior;
- derivative behavior;
- clamp and output limits;
- dynamic schedule;
- registry ownership;
- runtime configuration;
- actuator;
- reset behavior;
- test coverage;
- whether it is active, advisory, shadow-only, simulation-only, or dead.

Include:

- Box 6 entry/exit PID;
- continuous PA PID;
- continuous studies PID;
- studies-weight PIDs;
- governor outer loop;
- governor inner loop;
- V3 governor loop;
- AVR;
- dispatcher;
- ECS;
- sector dispatch;
- HRSG;
- Mark V;
- MiCOM/SEL;
- grid synchronizer;
- closed-loop derates;
- entry/exit shadow controllers;
- older Revision 0–4 PID systems.

## Parameter provenance

For every parameter found, determine:

- original revision;
- first introduction commit;
- later migrations;
- current registry name;
- whether it exists in Engine C;
- whether it exists only on another branch;
- whether it was calibrated;
- calibration dataset;
- calibration protocol;
- calibration result;
- whether the result was ever integrated;
- whether the current runtime actually consumes it.

Create a cross-revision mapping:

```text
old parameter
    -> renamed parameter
    -> registry parameter
    -> current runtime consumer
    -> current actuator
    -> current test
```

Identify duplicate parameter systems and determine which one is authoritative.

## Historical work reuse audit

Find all earlier work that may be reusable, including:

- parameterization commits;
- calibrated parameter JSON files;
- calibration summaries;
- three-year calibration runners;
- protocol v1/v2/v3 files;
- governor V3 branches;
- R4/R5 dynamic parameter modules;
- older AVR implementations;
- older dispatch implementations;
- completed sensitivity tests;
- prior cross-engine acceptance tests;
- archived worktrees;
- local-only branches;
- reports claiming “calibration complete.”

For each artifact state:

- exact path;
- revision;
- branch;
- commit;
- whether it is byte-identical to current code;
- whether it is newer or older than Engine C;
- whether it can be cherry-picked;
- whether it requires adaptation;
- whether it must not be reused.

## Revision-by-revision assessment

Produce separate assessments for:

### Revision 0

What controllers, parameters, tests, and calibration work exist? What remains reusable?

### Revision 1

What was added or changed? Which work migrated forward?

### Revision 2

Audit the original in-house and external orchestrators, PID systems, parameter registry, and calibration tooling.

### Revision 3

Audit HMM, protection relay, calibration and full-history systems.

### Revision 4

Audit production calibration, Optuna/Ray/CMA-ES tools, sealed parameters, and validation outputs.

### Revision 5

Audit the current plant, governor, AVR, dispatch, ECS, studies, Box 6, closed-loop and Engine A/B/C implementations.

For each revision, provide:

- completed work;
- incomplete work;
- migrated work;
- abandoned work;
- work that is better than the current implementation;
- work that must not be resurrected.

## Engine comparison

Compare the reusable logic and gaps across:

- Engine A;
- Engine B;
- Engine C.

Determine whether each engine uses:

- the same registry;
- the same controller implementation;
- the same parameter values;
- the same governor;
- the same AVR;
- the same dispatcher;
- the same exit authority;
- the same cross-session behavior;
- the same calibration protocol.

Identify behavior differences caused by execution adapters rather than strategy logic.

## Three-year and long-holding audit

Find every previous run that used:

- 48 symbols;
- full available history;
- one month;
- six months;
- one year;
- three years;
- multi-session or long-holding positions.

For every run, report:

- engine;
- revision;
- dataset;
- date range;
- symbols;
- bars;
- trades;
- P&L;
- parameters;
- protocol hash;
- whether it was calibration, validation, smoke testing, or production qualification.

Do not treat a 1,200-bar run as a three-year validation.

## Required output files

Create no source-code changes, but produce audit reports in a separate audit output directory:

- `REVISION_PROVENANCE_MATRIX.md`
- `CONTROLLER_CROSS_REVISION_INVENTORY.md`
- `PARAMETER_LINEAGE_MATRIX.csv`
- `CALIBRATION_ARTIFACT_INDEX.md`
- `ENGINE_A_B_C_COMPARISON.md`
- `REUSABLE_WORK_CANDIDATES.md`
- `DUPLICATE_OR_SUPERSEDED_WORK.md`
- `MISSING_WORK_AFTER_FULL_AUDIT.md`
- `GEMINI_REVIEW_OF_CLAUDE_PROGRAMME.md`
- `FINAL_R5_REUSE_PLAN.md`

## Final decision matrix

For every work item from the Claude programme, provide:

| Work item | Existing location | Revision | Commit | Current status | Reusable? | Porting work | New implementation needed? | Tests needed |
|---|---|---:|---|---|---|---|---|---|

## Required final conclusions

Answer clearly:

1. What has already been done and should not be repeated?
2. Which earlier revisions contain better or more complete implementations?
3. Which parameterization work can be ported directly?
4. Which work requires adaptation?
5. Which work is missing everywhere?
6. Which current Engine C claims are overstated?
7. Which calibration results are valid for the current code?
8. Which calibration results belong to older engines or obsolete protocols?
9. What is the minimum remaining implementation programme?
10. What exact files and commits should be reused?
11. What should be discarded?
12. What must be independently reviewed before merging?

Use exact paths, branches, commits, hashes, and line references. Clearly distinguish:

- source code from documentation;
- static parameterization from runtime parameterization;
- runtime dynamics from calibration;
- telemetry from actuation;
- simulation-only from active paper authority;
- historical results from current-engine results.

Do not claim that work is missing until all revisions and local copies have been searched. Do not claim that work is complete until the current runtime consumes it and an end-to-end test proves its actuator effect.
