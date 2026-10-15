# Agent work — recovered and indexed on 2026-09-24

Canonical location: `/home/srinivas/projects/zerodha-phase1/local_workspace/agent_outputs`.

## Findings

- Qwen: 14 original reports plus one backend benchmark recovered from `ECS_Complete/_local_review_reports`. Metadata identifies `qwen3-coder:30b`; a separate model called Qwen 3.8 has not been identified.
- All 36 source selections recorded in those reports match their recorded SHA-256 hashes using the review runner's UTF-8 and line-range rules. The duplicate reports under `ECS_GitHub` are byte-identical.
- Qwen report `review_report_20260828_170925.md` is invalid repeated output according to the existing source-verified summary. Preserve it as diagnostic evidence only. Its valid retry is `review_report_20260828_171132.md`.
- The Qwen reports concern August P01D safety reviews, benchmarks, and Item 3b research packages. They are historical advisory work, not a new R5 engine. Hash verification establishes provenance, not correctness of every recommendation. The existing verified summary explicitly records corrected model inaccuracies.
- Claude-attributed R5 BB05–BB06, BB07–BB08, three-controller, and corrected BB09–BB10 work is already integrated. Integration commits `9df4640`, `2292697`, `decef42`, and `89ee766` are ancestors of the current checkout. Original commit messages include Claude coauthor attribution. No replacement engine copy is needed.
- The historical workbook with Claude comments is preserved unchanged. Its spreadsheet content has not been substantively reviewed in this recovery.
- Other recovered agent work remains in `../recovery/backup_code_and_notes_20260923.zip`, with source paths in `../records/recovered-files.json`. Agent identity is not inferred from filenames or timestamps alone.

## Folder map

| Folder/file | Contents |
|---|---|
| `qwen/original_reports/` | Original reports and benchmark, byte-preserved |
| `qwen/report-index.json` | Tasks, model, backend, and status per report |
| `qwen/input-provenance-check.json` | 36 checked source selections |
| `qwen/reviewed_source_reference.zip` | Historical source files used by reviews; reference only |
| `claude/historical_review/` | Original PID architecture workbook with Claude comments |
| `r5/integrated_audits/` | Copies of six active controller/black-box audit documents |
| `r5/integration-history.txt` | Original and integration commit metadata |
| `context/` | Existing verified review summary, work assignments, and project plan |
| `inventory.json` | Copied file paths, source paths, byte sizes, and SHA-256 hashes |

No production code has been overwritten. These local records are excluded from Git through the existing `local_workspace/` exclusion. Original backup files remain intact. Work saved elsewhere or only in agent conversations is outside the verified scope of this recovery.

## Fresh R5 validation

2026-09-24: BB05–BB06, BB07–BB08, BB09–BB10, and three-controller parameterization test files: **118 passed**, 24 timedelta deprecation warnings, in 145.60 seconds. This validates the selected integrated R5 suites, not every historical agent recommendation.

Additional Claude laptop sessions and saved file versions: `/home/srinivas/projects/zerodha-phase1/local_workspace/agent_outputs/claude/laptop_sessions/README.md`.
