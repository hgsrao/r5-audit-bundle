import json, hashlib, csv, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARMS=['baseline','A_rr_boundary','B_pa_unsigned','C_quality_band','D_id_rr_removed','E_combined']
EXPECTED='311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d'
rows=[]
failures=[]
identities=[]
lines=['# Frozen Block 1 PA / admission isolation experiment','','Paper-only experimental policies. Trial000, 48 symbols, five sealed sessions, unchanged safety contract. No default promotion or holdout expansion.','','| Arm | Trades | BUY / SELL | Hold Q1 / median / Q3 (bars) | Gross R | Gross P&L | Costs | Net P&L | MTM DD % |','|---|---:|---|---|---:|---:|---:|---:|---:|']
for arm in ARMS:
 p=ROOT/arm
 m=json.loads((p/'run_manifest.json').read_text()); r=json.loads((p/'result.json').read_text()); receipt=json.loads((p/'research_arm_receipt.json').read_text()); s=r['summary']
 sha=hashlib.sha256((p/'ledger.csv').read_bytes()).hexdigest()
 unchanged=all(m['source_identity'][k]==m['source_identity_after'][k] for k in ('aggregate_sha256','file_count','git_head'))
 if m['status']!='COMPLETED' or not unchanged: failures.append(arm+': status/source')
 if arm=='baseline' and sha!=EXPECTED: failures.append('baseline ledger parity')
 accounting=s['passive_rejection_accounting']
 for stage,sides in accounting.items():
  for side,a in sides.items():
   if a['input']!=a['passed']+sum(a['rejects'].values()) or not a['accounting_closed']: failures.append(arm+': accounting '+stage+' '+side)
 identity=[m['protocol']['sha256'],m['params']['sha256'],m['slice_sha256'],s['block_fingerprint'],m['source_identity']['aggregate_sha256'],s['runtime_safety_contract'],m['universe'],m['data_view'],m['grid_inputs']['feeds'],m['grid_inputs']['manifest_file_sha256']]
 identities.append(identity)
 row=dict(arm=arm,summary=s,ledger_sha256=sha,source_unchanged=unchanged,receipt=receipt,manifest_identity=identity)
 rows.append(row)
 h=s['holding_duration_bars']; side=s['trades_by_side']
 lines.append(f"| {arm} | {s['completed_trades']} | {side.get('BUY',0)} / {side.get('SELL',0)} | {h['q1']} / {h['median']} / {h['q3']} | {s['gross_r_expectation']:.4f} | {s['gross_pnl']:.2f} | {s['total_costs']:.2f} | {s['net_pnl']:.2f} | {s['mtm_max_drawdown_percent']:.4f} |")
if any(x!=identities[0] for x in identities): failures.append('input/source/safety identity mismatch')
if len(set(x['receipt']['process_id'] for x in rows))!=len(ARMS): failures.append('process IDs not distinct')
lines += ['', '## Validation', '', 'Self-check failures: '+('none' if not failures else '; '.join(failures)), '', 'Baseline ledger SHA256: `'+rows[0]['ledger_sha256']+'`. Exact match to the accepted baseline: '+str(rows[0]['ledger_sha256']==EXPECTED)+'.', '', 'Runtime safety contract:', '', '```json',json.dumps(rows[0]['summary']['runtime_safety_contract'],indent=2),'```']
for row in rows:
 lines += ['', '## '+row['arm'], '', 'Actual arm actuation counters:', '', '```json',json.dumps(row['receipt']['arm_counters'],indent=2),'```','','| Stage | Side | Input | Pass | Reject | Closed |','|---|---|---:|---:|---:|---|']
 for stage,sides in row['summary']['passive_rejection_accounting'].items():
  for side,a in sides.items(): lines.append(f"| {stage} | {side} | {a['input']} | {a['passed']} | {sum(a['rejects'].values())} | {a['accounting_closed']} |")
 lines += ['', '| Gate12 reason family | BUY | SELL |', '|---|---:|---:|']
 counts={}
 for side,a in row['summary']['passive_rejection_accounting'].get('GATE12_REACHED',{}).items():
  for reason,n in a['rejects'].items():
   family=re.sub(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?','<number>',reason)
   counts.setdefault(family,{}); counts[family][side]=counts[family].get(side,0)+n
 for family,c in sorted(counts.items()): lines.append(f"| {family} | {c.get('BUY',0)} | {c.get('SELL',0)} |")
 lines += ['', 'Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `'+row['ledger_sha256']+'`.']
(ROOT/'COMPARISON.json').write_text(json.dumps(dict(failures=failures,arms=rows),indent=2)+'\n')
(ROOT/'COMPARISON.md').write_text('\n'.join(lines)+'\n')
print('SELF-CHECK FAILURES:',failures or 'none')
if failures: raise SystemExit(1)
