from pathlib import Path
import hashlib,json,shutil,subprocess
from datetime import datetime
ROOT=Path('/home/srinivas/projects/zerodha-phase1');w=ROOT/'local_workspace/stress_48'
p=json.loads((w/'pilot/summary.json').read_text());n=json.loads((w/'natural/summary.json').read_text());s=json.loads((w/'storm/summary.json').read_text());checks=json.loads((w/'lockout-checks.json').read_text())
assert n['symbols']==48 and n['replay_events']==48*739
assert n['result']['safety_violations']==0 and n['audit']['cap_violations']==0 and not n['result']['execution_halted']
assert n['audit']['pending_after_run']==0 and n['audit']['unclassified_after_run']==0
assert n['audit']['peak_open_positions']<=5 and s['audit']['peak_open_positions']<=5
assert all(checks.values())
storm_report=json.loads((w/'storm/report.json').read_text())
trip=s['audit']['fault_events'][0];reset=s['audit']['fault_events'][1]
# Use the certified topology mapping recorded by the engine's source module.
import sys
sys.path.insert(0,str(ROOT))
from revision5.topology import bay_for_symbol
inside=[t for t in storm_report['trades'] if datetime.fromisoformat(trip['timestamp']) < datetime.fromisoformat(t['entry_timestamp']) < datetime.fromisoformat(reset['timestamp'])]
unaffected_trades=[t for t in inside if bay_for_symbol(t['symbol'])!=trip['bay']]
assert unaffected_trades and all(bay_for_symbol(t['symbol'])!=trip['bay'] for t in inside)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()=='eb26df7f59a27da1f7f90f5ff1aa667a8545ab01'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
text='''# 48-symbol R5 stress replay — 2026-09-24

Checkpoint: `eb26df7f59a27da1f7f90f5ff1aa667a8545ab01`.
Annotated local tag: `r5-paper-apply-baseline-20260924`.
Git working tree clean at completion. No push, live order or calibration search.

## Engine and method

The driver is `local_workspace/stress_48/run_stress.py`, an instrumented subclass of the committed `Revision2ExternalEngineOrchestrator`. It runs the actual R5 PAPER_APPLY cap, native plant protection objects, shared portfolio, safety gates and costed synchronous paper broker. It is a direct Python replay harness, not an external backtesting platform or an Optuna parameter search. Normal indicator/model warmup and portfolio-weight calculations are part of engine execution.

All 48 stock CSVs and both NIFTY/VIX feeds were checked against the frozen source hashes. Grid timestamps are delayed by 15 minutes before causal selection. No stock price bars were fabricated. The latest common real-data date is 2026-08-13.

The **natural** run uses normal PA/ID/studies. The **storm** run deliberately overrides only upstream PA/ID/study demand to create simultaneous BUY requests on real price bars. MPC, sizing, admission caps, protection, order gates, fill handling and exits stay active. Storm P&L is not an alpha or profitability result.

## Measured results

| Metric | Natural replay | Forced-demand/ANSI-86 scenario |
|---|---:|---:|
'''
rows=[('Symbols',48,48),('Bars per symbol',800,180),('Replay events',n['replay_events'],s['replay_events']),('Load + hash verification seconds',round(n['load_seconds'],2),round(s['load_seconds'],2)),('Replay seconds',round(n['replay_seconds'],2),round(s['replay_seconds'],2)),('Total seconds',round(n['total_seconds'],2),round(s['total_seconds'],2)),('Completed trades',n['result']['completed_trades'],s['result']['completed_trades']),('Peak simultaneous candidates',n['audit']['max_batch'],s['audit']['max_batch']),('Peak open positions (limit 5)',n['audit']['peak_open_positions'],s['audit']['peak_open_positions']),('Peak gross exposure fraction (limit 0.5)',round(n['audit']['peak_gross_fraction'],4),round(s['audit']['peak_gross_fraction'],4)),('Cap violations',n['audit']['cap_violations'],s['audit']['cap_violations']),('Reported safety violations',n['result']['safety_violations'],s['result']['safety_violations']),('P95 timestamp-batch seconds',round(n['audit']['timestamp_processing_p95_seconds'],3),round(s['audit']['timestamp_processing_p95_seconds'],3)),('Max timestamp-batch seconds',round(n['audit']['timestamp_processing_max_seconds'],3),round(s['audit']['timestamp_processing_max_seconds'],3)),('Peak process memory MiB',round(n['audit']['peak_process_rss_mib'],1),round(s['audit']['peak_process_rss_mib'],1))]
for title,x,y in rows:text+=f'| {title} | {x} | {y} |\n'
text+=f'''\nPilot: 160 bars × 48 symbols, {p['total_seconds']:.2f} seconds total ({p['replay_seconds']:.2f} seconds replay). Natural and storm scenarios ran in separate processes with independent in-memory plants; their elapsed times overlap. Per-process timings include any machine contention. These are offline timings, not broker-network latency guarantees.

Natural sample net P&L: ₹{n['result']['net_pnl']:,.2f}. This stress run does not establish profitability or out-of-sample validation.

## ANSI-86 and selective dispatch

The test tripped `{s['audit']['fault_events'][0]['bay']}` at {s['audit']['fault_events'][0]['timestamp']}, while holding {', '.join(s['audit']['fault_events'][0]['held_symbols'])}. Three ordinary reclose attempts were rejected; no entry reached the broker in the locked bay. {s['audit']['locked_cap_rejections']} cap evaluations rejected locked-bay demand. Both existing positions exited during lockout. Other bays continued receiving positive caps ({s['audit']['unaffected_bay_positive_caps']} evaluations), and {len(unaffected_trades)} trades in unaffected bays entered strictly inside the lockout window (independently checked against trade timestamps in `lockout-trade-proof.json`). All five bays recorded fills over the scenario.

An explicit simulated operator reset at {s['audit']['fault_events'][1]['timestamp']} restored that bay, followed by {s['audit']['post_reset_entry_fills']} entry fills. Lockouts were not cleared automatically by market bars or new requests.

## Batch pressure and backlog finding

The engine has a **per-timestamp candidate batch, not a persistent waiting queue**. Candidates are ranked deterministically by current ID confidence, planned reward/risk and symbol tie-break. Every observed batch was reranked in reversed input order and produced the same order.

Storm dispositions: {json.dumps(s['audit']['candidate_dispositions'],sort_keys=True)}. Its 48-candidate peak saturated the configured five-position capacity; {s['audit']['candidate_reasons'].get('max_concurrent_positions',0)} requests were rejected for the position limit. Other requests were rejected earlier for symbol cooldown/trips or later by dispatch/gates. No PENDING or unclassified candidates remained in either scenario.

A rejection or DEFERRED observation is not a queued order and is not automatically retried later. This test verifies admission rejection under pressure and deterministic synchronous batch processing. It does **not** certify asynchronous broker queues, durable backlog recovery, queue fairness or network-timeout behavior; those mechanisms do not exist in this replay adapter.

## Reproduce

```bash
cd /home/srinivas/projects/zerodha-phase1
source /home/srinivas/.venvs/zerodha-phase1-r5/bin/activate
python local_workspace/stress_48/run_stress.py --scenario natural --bars 800
python local_workspace/stress_48/run_stress.py --scenario storm --bars 180
python local_workspace/stress_48/write_results.py
```

The harness, original logs, full trade reports, source hashes, and detailed summaries are stored under `local_workspace/stress_48/`. They are local test artifacts excluded from Git; the tested engine itself remains at the clean tagged checkpoint. `run-provenance.json` records the engine and harness hashes.

## Next milestone

The 48-symbol admission/lockout stress milestone passed within this defined offline scope. Next: connect causal replay events to native plant startup/protection/cooldown state, then implement durable receipts and restart reconciliation. A persistent admission queue would require an explicit expiry, revalidation and fairness policy; it should not be inferred from the existing deferred-candidate telemetry. Calibration and sealed out-of-sample testing remain later milestones.
'''
(w/'RESULTS.md').write_text(text)
summary={'status':'PASS','engine_commit':'eb26df7f59a27da1f7f90f5ff1aa667a8545ab01','tag':'r5-paper-apply-baseline-20260924','natural':n,'storm':s,'lockout_checks':checks,'working_tree_clean':True}
(w/'combined-summary.json').write_text(json.dumps(summary,indent=2))
artifacts=[]
for f in w.rglob('*'):
 if f.is_file() and f.name!='checksums.json':artifacts.append({'file':str(f.relative_to(w)),'bytes':f.stat().st_size,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()})
(w/'checksums.json').write_text(json.dumps(artifacts,indent=2))
out=Path('/home/srinivas/Documents/Codex/2026-09-24/referenced-chatgpt-conversation-this-is-an/outputs');shutil.copy2(w/'RESULTS.md',out/'R5-48-symbol-stress-results.md');shutil.copy2(w/'combined-summary.json',out/'R5-48-symbol-stress-summary.json')
print(json.dumps({'natural_total_seconds':n['total_seconds'],'natural_fills':n['result']['fills'],'storm_total_seconds':s['total_seconds'],'passed':True}))
