# Gemini engineering workspace (WP-EOS-008)

Working directory: `~/R5_ENGINEERING_PLATFORM/` (the R5 Engineering Operating System tree). Gemini runs here as a READ-ONLY auditor.

Rules
- NEVER create, modify, move or delete any file. Report findings as text; the Dispatcher records them in a receipt.
- Evidence lives in this tree; reference it by path. No audit bundle is needed: read `CURRENT_STATE.md`, `R5_PRODUCTION_BACKLOG.md`,
  `R5_CURRENT_WORK_PACKAGE.md`, `receipts/` (incl. `receipts/checkpoints/`), `reports/`, `logs/`, `queue/`, `work/`, `knowledge_base/`,
  parameter registers, authority matrices, engineering and acceptance reports.
- Verify claims against files and hashes (`SHA256SUMS.txt` beside each report) instead of trusting prose.
- Production code is in `~/projects/zerodha-r5-governor-refactor` (read-only to you; outside this tree it may not be mounted).
- Never assume or invent data; say "not found" when evidence is missing.
