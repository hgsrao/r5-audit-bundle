# Engineering Dispatcher V1: Workflow

1. **Submit.** `--submit file.json` validates the package and writes `queue/READY/<id>.json` (duplicate ids are refused in any state).
2. **Start.** The dispatcher recovers packages left RUNNING by an earlier crash (back to READY, `requeues` incremented).
3. **Select.** Highest priority, oldest first; packages with unfinished `depends_on` are skipped; the winner is moved to RUNNING.
4. **Route.** `package.worker`, else the first enabled worker for `package.type` in the routing table, else `default_worker`. A disabled or unknown
   worker yields a FAILED receipt with the routing error.
5. **Dispatch.** The worker adapter formats the prompt and performs exactly one request.
6. **Receipt.** JSON, Markdown and the raw response are written; `recent.json` and `logs/dispatcher.log` are updated.
7. **Complete.** The package moves to DONE (ok), REVIEW (ok + review requested) or FAILED, with a `dispatch` record inside the file.
8. **State.** The managed block in `CURRENT_STATE.md` shows queue counts, running ids and the ten most recent receipts.
9. **Next.** Repeat until READY is empty (`--drain`), after one package (`--once`) or until interrupted (`--watch`).

## Unexpected exit
Interrupt, SIGTERM or an internal error: RUNNING packages return to READY, `CURRENT_STATE.md` is refreshed, `R5_HANDOVER.md` is written (the previous
file is archived), and the exception propagates. Resume with `--drain`.

## Typical operator flow
```sh
python -m engineering_dispatcher.dispatcher --submit packages/WP-EOS-007.json
python -m engineering_dispatcher.dispatcher --drain
ls receipts/dispatcher/ ; tail logs/dispatcher.log
```

## Audit packages
Submit a package with `type: AUDIT` (no files or bundle needed). Step 4 routes it to the auditor (read-only); step 5 runs the CLI from the audit root; step 6 records
`audit_root` and the access mode in the receipt, the DISPATCH log event and the queue record. Everything else in the workflow is unchanged.
