"""WP-R5-001C-QUAL analysis. Offline: reads only the raw artefacts and the 48 file NAMES of the frozen universe directory.
No network, no credentials, no market-data file opened, raw files never written. Writes analysis_results.json, MISMATCHES.csv
and AUTHORITATIVE_METADATA_INDEX.csv next to this script."""
import collections
import csv
import gzip
import hashlib
import json
import os
import re
from decimal import Decimal

OUT = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(os.path.dirname(os.path.dirname(OUT)))
RAW = os.path.join(OUT, 'raw')
B_RAW = os.path.join(PLAT, 'reports/production/WP-R5-001B/raw')
B_TABLE = os.path.join(PLAT, 'reports/production/WP-R5-001B/AUTHORITATIVE_INSTRUMENT_METADATA.csv')
UNIVERSE_DIR = '/home/srinivas/projects/zerodha-phase1/data/frozen_48_1min_20230703_20260824'
AUTH = os.path.join(RAW, 'kite_connect_instruments_NSE.csv')
PRIOR = os.path.join(B_RAW, 'kite_instruments_NSE.csv')
NSE = os.path.join(B_RAW, 'NSE_CM_security_06102026.csv.gz')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


res = {}
mism = []  # (comparison, symbol, field, auth_value, other_value)

# ---- A. integrity
rec = json.load(open(os.path.join(RAW, 'ACQUISITION_RECORD.json')))
sums = {}
for line in open(os.path.join(RAW, 'SHA256SUMS.txt')):
    if line.strip():
        h, n = line.split(None, 1)
        sums[n.strip()] = h
integ = {}
for name in sorted(os.listdir(RAW)):
    p = os.path.join(RAW, name)
    got = sha256(p)
    e = dict(sha256=got, size=os.path.getsize(p))
    e['sha_vs_SHA256SUMS'] = (got == sums[name]) if name in sums else 'NOT_LISTED(self-referencing or absent)'
    if name == rec['raw_file']:
        e['sha_vs_ACQUISITION_RECORD'] = got == rec['sha256']
        e['size_vs_ACQUISITION_RECORD'] = e['size'] == rec['size_bytes']
    integ[name] = e
res['integrity_raw_001C'] = integ
res['sums_entries_without_file'] = [n for n in sums if n not in integ]
res['prior_files'] = {n: dict(sha256=sha256(os.path.join(B_RAW, n)), size=os.path.getsize(os.path.join(B_RAW, n)))
                      for n in ('kite_instruments_NSE.csv', 'NSE_CM_security_06102026.csv.gz')}
res['auth_bytes_identical_to_prior_kite'] = open(AUTH, 'rb').read() == open(PRIOR, 'rb').read()

auth = list(csv.DictReader(open(AUTH, newline='')))
prior = list(csv.DictReader(open(PRIOR, newline='')))
with gzip.open(NSE, 'rt', newline='') as fh:
    nse = list(csv.DictReader(fh))
res['rows'] = dict(kite_authenticated=len(auth), kite_prior=len(prior), nse_security_master=len(nse),
                   acquisition_record_instrument_rows=rec['instrument_rows'],
                   auth_nse_eq=sum(1 for r in auth if r['exchange'] == 'NSE' and r['segment'] == 'NSE' and r['instrument_type'] == 'EQ'),
                   auth_indices=sum(1 for r in auth if r['segment'] == 'INDICES'))
res['rows']['auth_rows_match_record'] = len(auth) == rec['instrument_rows']

# ---- universe from file names only
pat = re.compile(r'^NSE_(.+)_minute_2023-07-03_2026-08-24\.csv$')
syms = sorted(pat.match(f).group(1) for f in os.listdir(UNIVERSE_DIR) if pat.match(f))
assert len(syms) == 48 and len(set(syms)) == 48
res['universe'] = syms

by = collections.defaultdict(list)
for r in auth:
    if r['exchange'] == 'NSE' and r['segment'] == 'NSE' and r['instrument_type'] == 'EQ':
        by[r['tradingsymbol']].append(r)
any_auth = collections.defaultdict(list)
for r in auth:
    any_auth[r['tradingsymbol']].append(r)
nse_eq = collections.defaultdict(list)
nse_any = collections.defaultdict(list)
for r in nse:
    nse_any[r['TckrSymb']].append(r)
    if r['SctySrs'] == 'EQ':
        nse_eq[r['TckrSymb']].append(r)
prior_eq = collections.defaultdict(list)
for r in prior:
    if r['exchange'] == 'NSE' and r['segment'] == 'NSE' and r['instrument_type'] == 'EQ':
        prior_eq[r['tradingsymbol']].append(r)
btab = {r['tradingsymbol']: r for r in csv.DictReader(open(B_TABLE, newline=''))}
res['prior_table_rows'] = len(btab)

# ---- B. coverage
FIELDS = ['instrument_token', 'tradingsymbol', 'tick_size', 'lot_size', 'segment', 'exchange']
cov = dict(covered=[], missing=[], duplicate=[], non_EQ_only=[], field_missing={})
for s in syms:
    n = len(by[s])
    if n == 1:
        cov['covered'].append(s)
        miss = [f for f in FIELDS if not (by[s][0][f] or '').strip()]
        # tick/lot must also be positive
        for f in ('tick_size', 'lot_size'):
            if f not in miss and Decimal(by[s][0][f]) <= 0:
                miss.append(f + '<=0')
        if miss:
            cov['field_missing'][s] = miss
    elif n > 1:
        cov['duplicate'].append(s)
    else:
        (cov['non_EQ_only'] if any_auth[s] else cov['missing']).append(s)
res['coverage_auth'] = cov
res['nse_coverage'] = dict(
    covered=[s for s in syms if len(nse_eq[s]) == 1], missing=[s for s in syms if not nse_any[s]],
    duplicate=[s for s in syms if len(nse_eq[s]) > 1], non_EQ_only=[s for s in syms if nse_any[s] and not nse_eq[s]])

# ---- C. cross-checks (every mismatch recorded)
# C1 authenticated vs prior Kite dump: whole-file row-level diff on every column
fl = list(auth[0].keys())
res['columns_equal'] = fl == list(prior[0].keys())
pkey = collections.defaultdict(list)
for r in prior:
    pkey[r['instrument_token']].append(r)
akeys = set()
nd = 0
for r in auth:
    akeys.add(r['instrument_token'])
    o = pkey.get(r['instrument_token'])
    if not o or len(o) != 1:
        nd += 1
        mism.append(('auth_vs_prior_kite', r['tradingsymbol'], 'instrument_token_presence', r['instrument_token'], 'absent_or_dup_in_prior'))
        continue
    for c in fl:
        if r[c] != o[0][c]:
            nd += 1
            mism.append(('auth_vs_prior_kite', r['tradingsymbol'], c, r[c], o[0][c]))
for t in pkey:
    if t not in akeys:
        nd += 1
        mism.append(('auth_vs_prior_kite', pkey[t][0]['tradingsymbol'], 'instrument_token_presence', 'absent_in_auth', t))
res['auth_vs_prior_whole_file_cell_diffs'] = nd

# C2 per-symbol: auth vs prior Kite 48 (tick, lot, token, symbol), vs NSE, vs prior 48-row table
checks = collections.Counter()
ticks = collections.Counter()
lots = collections.Counter()
for s in syms:
    if len(by[s]) != 1:
        continue
    a = by[s][0]
    ticks[str(Decimal(a['tick_size']))] += 1
    lots[a['lot_size']] += 1
    p = prior_eq.get(s)
    if p is None or len(p) != 1:
        mism.append(('auth_vs_prior_kite', s, 'row_presence', 'present', 'absent_or_dup'))
    else:
        for f in ('tradingsymbol', 'instrument_token', 'exchange_token', 'tick_size', 'lot_size'):
            checks['prior_kite_' + f] += 1
            if Decimal(a[f]) != Decimal(p[0][f]) if f in ('tick_size', 'lot_size', 'instrument_token', 'exchange_token') else a[f] != p[0][f]:
                if not any(m[0] == 'auth_vs_prior_kite' and m[1] == s and m[2] == f for m in mism):
                    mism.append(('auth_vs_prior_kite', s, f, a[f], p[0][f]))
    ne = nse_eq[s]
    if len(ne) != 1:
        mism.append(('auth_vs_nse_master', s, 'row_presence', 'present', 'EQ rows=%d' % len(ne)))
    else:
        n = ne[0]
        if n['TckrSymb'] != a['tradingsymbol']:
            mism.append(('auth_vs_nse_master', s, 'symbol', a['tradingsymbol'], n['TckrSymb']))
        nt = Decimal(int(n['BidIntrvl'])) / Decimal(100)
        checks['nse_tick'] += 1
        if Decimal(a['tick_size']) != nt:
            mism.append(('auth_vs_nse_master', s, 'tick_size(BidIntrvl/100)', a['tick_size'], '%s (BidIntrvl=%s paise)' % (nt, n['BidIntrvl'])))
        checks['nse_lot'] += 1
        if int(a['lot_size']) != int(n['NewBrdLotQty']):
            mism.append(('auth_vs_nse_master', s, 'lot_size(NewBrdLotQty)', a['lot_size'], n['NewBrdLotQty']))
        checks['nse_token'] += 1
        if a['exchange_token'] != n['FinInstrmId']:
            mism.append(('auth_vs_nse_master', s, 'exchange_token(FinInstrmId)', a['exchange_token'], n['FinInstrmId']))
        checks['token_formula'] += 1
        if int(a['instrument_token']) != int(a['exchange_token']) * 256 + 1:
            mism.append(('auth_internal', s, 'instrument_token!=exchange_token*256+1', a['instrument_token'], str(int(a['exchange_token']) * 256 + 1)))
    b = btab.get(s)
    if b is None:
        mism.append(('auth_vs_prior_48row_table', s, 'row_presence', 'present', 'absent'))
    else:
        for f in ('tradingsymbol', 'exchange', 'instrument_token', 'exchange_token', 'segment', 'instrument_type'):
            checks['table_' + f] += 1
            if a[f] != b[f]:
                mism.append(('auth_vs_prior_48row_table', s, f, a[f], b[f]))
        for f in ('tick_size', 'lot_size'):
            checks['table_' + f] += 1
            if Decimal(a[f]) != Decimal(b[f]):
                mism.append(('auth_vs_prior_48row_table', s, f, a[f], b[f]))
res['checks_performed_counts'] = dict(checks)
res['ticks_48'] = dict(ticks)
res['lots_48'] = dict(lots)
res['mismatch_count'] = len(mism)
res['mismatch_by_comparison'] = dict(collections.Counter(m[0] for m in mism))

with open(os.path.join(OUT, 'MISMATCHES.csv'), 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['comparison', 'symbol', 'field', 'authenticated_kite_value', 'other_source_value'])
    w.writerows(mism)

# ---- index
with open(os.path.join(OUT, 'AUTHORITATIVE_METADATA_INDEX.csv'), 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['row_type', 'symbol_or_path', 'instrument_token', 'exchange_token', 'tradingsymbol', 'exchange', 'segment', 'instrument_type',
                'tick_size', 'lot_size', 'name', 'nse_isin', 'nse_bid_interval_paise', 'nse_tick_agrees', 'nse_lot_agrees', 'prior_kite_agrees',
                'sha256', 'size_bytes', 'role', 'source', 'as_of_utc', 'status'])
    for s in syms:
        a = by[s][0]
        n = nse_eq[s][0]
        p = prior_eq[s][0]
        w.writerow(['symbol', s, a['instrument_token'], a['exchange_token'], a['tradingsymbol'], a['exchange'], a['segment'], a['instrument_type'],
                    a['tick_size'], a['lot_size'], a['name'], n['ISIN'], n['BidIntrvl'],
                    str(Decimal(a['tick_size']) == Decimal(int(n['BidIntrvl'])) / 100).upper(),
                    str(int(a['lot_size']) == int(n['NewBrdLotQty'])).upper(),
                    str(all(a[c] == p[c] for c in fl)).upper(),
                    '', '', '', 'Kite Connect authenticated GET https://api.kite.trade/instruments/NSE', rec['download_finished_utc'],
                    'AUTHORITATIVE_BASELINE(TRAIN_REPLAY_DIAGNOSTIC; TRAIN stability under assumption A-META-001, not verified)'])
    files = [(AUTH, 'raw_authoritative_baseline', 'Kite Connect authenticated GET https://api.kite.trade/instruments/NSE', rec['download_finished_utc']),
             (AUTH + '.headers.json', 'raw_response_headers', 'Kite Connect response headers', rec['download_finished_utc']),
             (os.path.join(RAW, 'ACQUISITION_RECORD.json'), 'raw_acquisition_record', 'scripts/acquire_kite_metadata.py', rec['download_finished_utc']),
             (os.path.join(RAW, 'SHA256SUMS.txt'), 'raw_checksums', 'scripts/acquire_kite_metadata.py', rec['download_finished_utc']),
             (PRIOR, 'crosscheck_prior_kite_unauthenticated', 'WP-R5-001B raw', '2026-10-07T05:31:13Z'),
             (NSE, 'crosscheck_nse_security_master', 'WP-R5-001B raw', '2026-10-07T05:31:13Z'),
             (B_TABLE, 'crosscheck_prior_48row_table', 'WP-R5-001B derived', '2026-10-07')]
    for p, role, src, t in files:
        w.writerow(['file', os.path.relpath(p, PLAT), '', '', '', '', '', '', '', '', '', '', '', '', '', '', sha256(p), os.path.getsize(p), role, src, t, ''])

with open(os.path.join(OUT, 'analysis_results.json'), 'w') as f:
    json.dump(res, f, indent=1, sort_keys=True, default=str)
print(json.dumps(res, indent=1, sort_keys=True, default=str)[:6000])
