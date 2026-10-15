import json, csv, collections, copy, os, sys, datetime
sys.path.insert(0, os.path.dirname(__file__))
from spec import S, MATH, SIM, NQ, UNK

REPO = '/home/srinivas/projects/zerodha-r5-governor-refactor'
REGP = REPO + '/docs/r5_remediation_project/R5_PARAMETER_REGISTER.json'
OUT = '/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-001'
os.makedirs(OUT, exist_ok=True)
CLASSES = ["CERTIFIED_METADATA", "MATHEMATICAL_DERIVATION", "HISTORICAL_CALIBRATION", "ENGINEERING_POLICY",
           "SIMULATION_ONLY", "NOT_QUALIFIED", "UNKNOWN"]

reg = json.load(open(REGP))
orig = [x for x in reg['parameters'] if 'closed' in x]
assert len(orig) == 62
ids = [x['id'] for x in orig]
missing = [i for i in ids if i not in S]
extra = [i for i in S if i not in ids]
assert not missing and not extra, (missing, extra)

ENG_OWNER = "Engineering: Codex (Claude implements) per backlog; no named human owner is recorded in any source"
rows = []
for x in orig:
    s = S[x['id']]
    active = x['active_in_production']
    closed = x['closed']
    if s['auth'] in (NQ, UNK):
        auth_owner = "UNASSIGNED (no owner-approval record exists)"
    elif s['auth'] == MATH:
        auth_owner = "Engineering (code-level derivation; no external owner required)"
    else:
        auth_owner = "Engineering (isolation evidence); no production owner required while isolated"
    if x['final_state'] == 'UNRESOLVED':
        status = f"OPEN - active in production path ({x['runtime_reachability']}); authority {s['auth']}; register final_state UNRESOLVED / closed NO"
    elif s['auth'] in (NQ, UNK):
        status = (f"Register says closed={closed} ({x['final_state']}) but authority is {s['auth']} - closure does NOT establish authority; "
                  f"active_in_production={active}")
    else:
        status = f"Closed in register ({x['final_state']}, active_in_production={active}); authority {s['auth']} supported by opened evidence"
    rows.append({
        "Parameter": x['parameter'], "ID": x['id'], "Original class": x['original_class'],
        "Location": s['vloc'], "Location verification": s['lnote'],
        "Authority": s['auth'], "Evidence": s['evid'],
        "Owner": f"{ENG_OWNER}; backlog/proposed package: {s['wp']}; authority owner: {auth_owner}",
        "Dependent components": s['deps'], "Current status": status,
        "Blocking evidence still required": s['block'],
        "Register active_in_production": active, "Register final_state": x['final_state'], "Register closed": closed,
        "Register runtime_reachability": x['runtime_reachability'],
        "_authority_owner": auth_owner, "_wp": s['wp'],
    })

counts = collections.Counter(r['Authority'] for r in rows)
assert sum(counts.values()) == 62
cls_h = collections.Counter((r['Original class'], r['Authority']) for r in rows)
act = [r for r in rows if r['Register final_state'] == 'UNRESOLVED']
act_counts = collections.Counter(r['Authority'] for r in act)
act_hij = collections.Counter(r['Original class'] for r in act)
assert len(act) == 34 and act_hij == {'H': 11, 'I': 19, 'J': 4}, (len(act), act_hij)
closed_nq = [r for r in rows if r['Register closed'] == 'YES' and r['Authority'] in (NQ, UNK)]

public_cols = ["Parameter", "ID", "Location", "Authority", "Evidence", "Owner", "Dependent components", "Current status",
               "Blocking evidence still required"]
extra_cols = ["Original class", "Location verification", "Register active_in_production", "Register final_state", "Register closed",
              "Register runtime_reachability"]
allcols = public_cols + extra_cols

# --- CSV
with open(OUT + '/PRODUCTION_PARAMETER_CLOSURE_MATRIX.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=allcols, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow(r)

# --- JSON
meta = {
    "work_package": "WP-R5-001", "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "repo_root": REPO, "repo_branch_commit": "feature/ir02a-parameter-closure @ 59371ff (working tree dirty; read-only)",
    "source_register": REGP, "rows": 62, "authority_class_counts": {c: counts.get(c, 0) for c in CLASSES},
    "active_unresolved_rows": 34, "active_unresolved_authority_counts": {c: act_counts.get(c, 0) for c in CLASSES},
    "note": "Evidence paths are repo-relative (prefix R5:) to repo_root. UNKNOWN/NOT_QUALIFIED are never approvals. No production readiness is claimed.",
}
json.dump({"meta": meta, "rows": [{k: v for k, v in r.items() if not k.startswith('_')} for r in rows]},
          open(OUT + '/PRODUCTION_PARAMETER_CLOSURE_MATRIX.json', 'w'), indent=2)

# --- MD
def esc(t):
    return str(t).replace('|', '\\|').replace('\n', ' ')

md = ["# Production Parameter Closure Matrix - WP-R5-001", "",
      f"Generated {meta['generated_utc']}. Source: `R5_PARAMETER_REGISTER.json` (62 original H/I/J rows) at R5 `feature/ir02a-parameter-closure` @ 59371ff "
      "(working tree dirty; read-only review). Evidence paths marked `R5:` are relative to `/home/srinivas/projects/zerodha-r5-governor-refactor`.", "",
      "Authority classes: CERTIFIED_METADATA, MATHEMATICAL_DERIVATION, HISTORICAL_CALIBRATION, ENGINEERING_POLICY, SIMULATION_ONLY, NOT_QUALIFIED, UNKNOWN. "
      "NOT_QUALIFIED/UNKNOWN are not approvals. UNKNOWN is used only where the origin and owner of the value cannot be established (here J-02, J-04); "
      "NOT_QUALIFIED where the value's nature is known but qualifying evidence is absent.", "",
      "## Counts by authority class (computed mechanically)", "", "| Authority | Rows (62) | Of which active-unresolved (34) |", "|---|---:|---:|"]
for c in CLASSES:
    md.append(f"| {c} | {counts.get(c, 0)} | {act_counts.get(c, 0)} |")
md += [f"| **Total** | **{sum(counts.values())}** | **{sum(act_counts.values())}** |", "",
       "## Matrix", "", "| " + " | ".join(public_cols) + " |", "|" + "---|" * len(public_cols)]
for r in rows:
    md.append("| " + " | ".join(esc(r[c]) for c in public_cols) + " |")
md += ["", "## Location verification notes (register citation vs working-tree source)", "", "| ID | Note |", "|---|---|"]
for r in rows:
    md.append(f"| {r['ID']} | {esc(r['Location verification'])} |")
open(OUT + '/PRODUCTION_PARAMETER_CLOSURE_MATRIX.md', 'w').write("\n".join(md) + "\n")

# --- Updated register copy
newreg = copy.deepcopy(reg)
byid = {r['ID']: r for r in rows}
touched = 0
for x in newreg['parameters']:
    r = byid.get(x['id']) if 'closed' in x else None
    if r:
        x['authority_class'] = r['Authority']
        x['authority_evidence'] = r['Evidence']
        x['authority_owner'] = r['_authority_owner']
        x['authority_status'] = r['Current status']
        touched += 1
assert touched == 62
# integrity: only the four fields were added, only on the 62 rows
for a, b in zip(reg['parameters'], newreg['parameters']):
    added = set(b) - set(a)
    assert added <= {'authority_class', 'authority_evidence', 'authority_owner', 'authority_status'}
    assert (len(added) == 4) == ('closed' in a)
    assert all(a[k] == b[k] for k in a)
json.dump(newreg, open(OUT + '/UPDATED_PARAMETER_REGISTER.json', 'w'), indent=1)

# --- Updated provenance audit
orig_audit = open(REPO + '/docs/r5_remediation_project/R5_PARAMETER_PROVENANCE_AUDIT.md').read()
au = ["# Updated R5 Parameter Provenance Audit - WP-R5-001 authority overlay", "",
      f"Generated {meta['generated_utc']} by script `/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-001/build_wp_r5_001.py` (counts computed from "
      "`UPDATED_PARAMETER_REGISTER.json`; per-class counts verified to sum to 62).", "",
      "This document overlays, and does not replace, `R5_PARAMETER_PROVENANCE_AUDIT.md` (reproduced unchanged below). The repository copy was not edited.", "",
      "## Authority class counts (62 original H/I/J rows)", "", "| Authority class | All 62 | H | I | J | Active-unresolved (34) |", "|---|---:|---:|---:|---:|---:|"]
for c in CLASSES:
    au.append(f"| {c} | {counts.get(c, 0)} | {cls_h.get(('H', c), 0)} | {cls_h.get(('I', c), 0)} | {cls_h.get(('J', c), 0)} | {act_counts.get(c, 0)} |")
au.append(f"| **Sum** | **{sum(counts.values())}** | **{sum(v for (k, _), v in cls_h.items() if k == 'H')}** | **{sum(v for (k, _), v in cls_h.items() if k == 'I')}** | **{sum(v for (k, _), v in cls_h.items() if k == 'J')}** | **{sum(act_counts.values())}** |")
au += ["", f"Active-unresolved rows (register final_state UNRESOLVED): {len(act)} = H {act_hij['H']} / I {act_hij['I']} / J {act_hij['J']} - UNCHANGED. "
       "No count was reduced; no class other than NOT_QUALIFIED/UNKNOWN was granted to any of them.", "",
       "Zero rows hold CERTIFIED_METADATA, HISTORICAL_CALIBRATION or ENGINEERING_POLICY: no installed hashed metadata artefact, no calibration receipt "
       "and no opened owner-approval record supports any of the 62 rows.", "",
       f"Closed-in-register rows whose authority is nevertheless NOT_QUALIFIED/UNKNOWN: {len(closed_nq)} ({', '.join(r['ID'] for r in closed_nq)}). "
       "Closure (P1/P2/P4 final_state) means the production path was isolated, fail-closed or removed; it is not authority.", "",
       "## Row dispositions", "", "| ID | Class | Authority | Register state | Active in prod |", "|---|---|---|---|---|"]
for r in rows:
    au.append(f"| {r['ID']} | {r['Original class']} | {r['Authority']} | {r['Register final_state']}/closed={r['Register closed']} | {r['Register active_in_production']} |")
au += ["", "---", "## Original provenance audit (unchanged, for reference)", "", orig_audit]
open(OUT + '/UPDATED_PROVENANCE_AUDIT.md', 'w').write("\n".join(au) + "\n")

print("counts", dict(counts), "sum", sum(counts.values()))
print("active counts", dict(act_counts))
print("closed but NQ/UNK", [r['ID'] for r in closed_nq])
print("by class/orig", dict(cls_h))
json.dump({"counts": counts, "active": act_counts, "closed_nq": [r['ID'] for r in closed_nq]}, open(OUT + '/_counts.json', 'w'))
