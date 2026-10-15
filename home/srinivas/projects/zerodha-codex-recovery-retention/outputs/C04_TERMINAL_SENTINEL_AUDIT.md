# F-ROOT-007 terminal reconciliation repair

The external replay clock excludes the last frame row (`range(warmup, len(bars)-1)`) because it is forward execution context. The old generic terminal CLOSE read that excluded row's close/timestamp anyway; worker Block 1 may place this row in the next unselected session.

Admission now rejects any proposal whose next fill row is the excluded final forward-context row, before ID/admission work. A final-only strong synthetic PA signal on truncated same-session historical inputs therefore yields no fill and no terminal abort.

The repaired orchestrator records the last actually processed index independently for each symbol and terminal CLOSE uses that bar. PERSIST branch remains ahead of this logic and is unchanged. If no processed observation exists, or the authoritative entry-fill timestamp is later than that observation, it halts without inventing a past exit. No admission/risk parameter or sealed V3 code changes.

Evidence in `tests/test_r5_terminal_sentinel.py`: a real derived TITAN historical admission/fill, with ordinary exit management deliberately disabled only in the boundary fixture, closes at the last processed timestamp/price. Changing excluded sentinel OHLC to 99,999 and timestamp to the next day produces identical terminal ledger. A second deliberate future-entry metadata fault verifies halt with real position still open, no completed trade, and no fabricated exit fill.

This intentionally corrects economics for trades that reach generic terminal CLOSE. It does not claim old sentinel-priced terminal reference ledgers remain identical or alter their files.
