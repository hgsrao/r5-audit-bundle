"""WP-R5-001B qualification analysis. Reads only the two raw artefacts and the 48 file NAMES of the frozen universe directory.
No network, no market-data file is opened. Writes AUTHORITATIVE_INSTRUMENT_METADATA.csv, TRAIN_INFILE_EVIDENCE.csv and
analysis_results.json next to this script."""
import collections
import csv
import datetime
import gzip
import hashlib
import json
import os
import re
from decimal import Decimal

OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, 'raw')
KITE = os.path.join(RAW, 'kite_instruments_NSE.csv')
NSE = os.path.join(RAW, 'NSE_CM_security_06102026.csv.gz')
UNIVERSE_DIR = '/home/srinivas/projects/zerodha-phase1/data/frozen_48_1min_20230703_20260824'
EXPECT = {
    KITE: ('536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f', 686374),
    NSE: ('0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803', 1259539),
}
TRAIN_START = datetime.date(2023, 9, 1)
TRAIN_END_EXCL = datetime.date(2025, 7, 1)
E80 = datetime.datetime(1980, 1, 1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def tick_text(value):
    d = Decimal(str(value))
    if d.as_tuple().exponent > -2:
        d = d.quantize(Decimal('0.01'))
    return format(d.normalize() if d.as_tuple().exponent < -2 else d, 'f')


def nse_date(v):
    v = (v or '').strip()
    if not v or v == '0':
        return ''
    return (E80 + datetime.timedelta(seconds=int(v))).strftime('%Y-%m-%d')


res = {}
# ---- A. integrity
integ = {}
for p, (esha, esize) in EXPECT.items():
    got, size = sha256(p), os.path.getsize(p)
    integ[os.path.relpath(p, OUT)] = dict(sha256=got, size=size, sha_match=got == esha, size_match=size == esize)
res['integrity'] = integ

kite = list(csv.DictReader(open(KITE, newline='')))
with gzip.open(NSE, 'rt', newline='') as fh:
    nse = list(csv.DictReader(fh))
res['kite_rows'] = len(kite)
res['nse_rows'] = len(nse)
res['kite_segment_type'] = {'%s|%s' % k: v for k, v in collections.Counter((r['segment'], r['instrument_type']) for r in kite).items()}
res['kite_nse_equity'] = sum(1 for r in kite if r['exchange'] == 'NSE' and r['segment'] == 'NSE' and r['instrument_type'] == 'EQ')
res['nse_series_top'] = collections.Counter(r['SctySrs'] for r in nse).most_common(8)
res['nse_eq_rows'] = sum(1 for r in nse if r['SctySrs'] == 'EQ')
res['nse_tickSz_nonempty_EQ'] = sum(1 for r in nse if r['SctySrs'] == 'EQ' and r['TickSz'].strip())

# ---- universe
pat = re.compile(r'^NSE_(.+)_minute_2023-07-03_2026-08-24\.csv$')
syms = sorted(pat.match(f).group(1) for f in os.listdir(UNIVERSE_DIR) if pat.match(f))
assert len(syms) == 48 and len(set(syms)) == 48
res['universe'] = syms

kite_eq = collections.defaultdict(list)
for r in kite:
    if r['exchange'] == 'NSE' and r['segment'] == 'NSE' and r['instrument_type'] == 'EQ':
        kite_eq[r['tradingsymbol']].append(r)
kite_any = collections.defaultdict(list)
for r in kite:
    kite_any[r['tradingsymbol']].append(r)
nse_eq = collections.defaultdict(list)
nse_any = collections.defaultdict(list)
for r in nse:
    nse_any[r['TckrSymb']].append(r)
    if r['SctySrs'] == 'EQ':
        nse_eq[r['TckrSymb']].append(r)

# ---- B coverage
cov = dict(kite_covered=[], kite_missing=[], kite_dup=[], kite_nonEQ_only=[], nse_covered=[], nse_missing=[], nse_dup=[], nse_nonEQ_only=[])
for s in syms:
    kc = len(kite_eq[s])
    if kc == 1:
        cov['kite_covered'].append(s)
    elif kc > 1:
        cov['kite_dup'].append(s)
    else:
        (cov['kite_nonEQ_only'] if kite_any[s] else cov['kite_missing']).append(s)
    nc = len(nse_eq[s])
    if nc == 1:
        cov['nse_covered'].append(s)
    elif nc > 1:
        cov['nse_dup'].append(s)
    else:
        (cov['nse_nonEQ_only'] if nse_any[s] else cov['nse_missing']).append(s)
res['coverage'] = cov
res['other_series_rows_for_48'] = {s: [r['SctySrs'] for r in nse_any[s] if r['SctySrs'] != 'EQ'] for s in syms if [r for r in nse_any[s] if r['SctySrs'] != 'EQ']}

# ---- C cross-validation (48)
disagree = []
rows = []
ticks48 = collections.Counter()
lots48 = collections.Counter()
extra = dict(exchange_token_vs_FinInstrmId=0, token_formula=0, name_diff=[], band_tick_ok=0, delflg=collections.Counter(), status=collections.Counter())
for s in syms:
    k = kite_eq[s][0]
    n = nse_eq[s][0]
    bid = int(n['BidIntrvl'])
    nse_tick = Decimal(bid) / Decimal(100)
    kt = Decimal(k['tick_size'])
    t_ok = kt == nse_tick
    l_ok = int(k['lot_size']) == int(n['NewBrdLotQty'])
    if not t_ok or not l_ok:
        disagree.append(dict(symbol=s, kite_tick=k['tick_size'], nse_tick=str(nse_tick), kite_lot=k['lot_size'], nse_lot=n['NewBrdLotQty']))
    ticks48[tick_text(k['tick_size'])] += 1
    lots48[k['lot_size']] += 1
    extra['exchange_token_vs_FinInstrmId'] += int(k['exchange_token'] == n['FinInstrmId'])
    extra['token_formula'] += int(int(k['instrument_token']) == int(k['exchange_token']) * 256 + 1)
    if k['name'].strip().upper() != n['FinInstrmNm'].strip().upper():
        extra['name_diff'].append((s, k['name'], n['FinInstrmNm']))
    lo, hi = n['PricRg'].split('-')
    extra['band_tick_ok'] += int(Decimal(lo) % nse_tick == 0 and Decimal(hi) % nse_tick == 0)
    extra['delflg'][n['DelFlg']] += 1
    extra['status'][n['SctyStsNrmlMkt']] += 1
    rows.append(dict(
        tradingsymbol=s, exchange=k['exchange'], instrument_token=k['instrument_token'], exchange_token=k['exchange_token'],
        tick_size=tick_text(k['tick_size']), lot_size=k['lot_size'], segment=k['segment'], instrument_type=k['instrument_type'],
        expiry='', strike='', underlying='', name=k['name'], isin=n['ISIN'], nse_bid_interval_paise=n['BidIntrvl'],
        nse_series=n['SctySrs'], kite_nse_tick_agrees='TRUE' if t_ok else 'FALSE',
        source_primary='Kite Connect instruments dump NSE (GET https://api.kite.trade/instruments/NSE)',
        source_primary_sha256=integ['raw/kite_instruments_NSE.csv']['sha256'],
        source_secondary='NSE CM security master 06-Oct-2026 (GET https://nsearchives.nseindia.com/content/cm/NSE_CM_security_06102026.csv.gz)',
        source_secondary_sha256=integ['raw/NSE_CM_security_06102026.csv.gz']['sha256'],
        as_of_primary='2026-10-07', as_of_secondary='2026-10-06'))
res['tick_disagreements_or_lot'] = disagree
res['agree_tick_lot'] = len(syms) - len(disagree)
res['distinct_ticks_48'] = dict(ticks48)
res['distinct_lots_48'] = dict(lots48)
extra['delflg'] = dict(extra['delflg'])
extra['status'] = dict(extra['status'])
res['extra_checks_48'] = extra

cols = ['tradingsymbol', 'exchange', 'instrument_token', 'exchange_token', 'tick_size', 'lot_size', 'segment', 'instrument_type', 'expiry', 'strike',
        'underlying', 'name', 'isin', 'nse_bid_interval_paise', 'nse_series', 'kite_nse_tick_agrees', 'source_primary', 'source_primary_sha256',
        'source_secondary', 'source_secondary_sha256', 'as_of_primary', 'as_of_secondary']
with open(os.path.join(OUT, 'AUTHORITATIVE_INSTRUMENT_METADATA.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)

# ---- population cross-check of BidIntrvl reading (all NSE-EQ symbols that also have a unique Kite NSE EQ row)
pop = collections.Counter()
for sym, ns in nse_eq.items():
    ks = kite_eq.get(sym, [])
    if len(ns) != 1 or len(ks) != 1:
        pop['unmatched_or_dup'] += 1
        continue
    n, k = ns[0], ks[0]
    pop['matched'] += 1
    if Decimal(k['tick_size']) == Decimal(int(n['BidIntrvl'])) / 100:
        pop['tick_agree'] += 1
    else:
        pop['tick_disagree'] += 1
    if int(k['lot_size']) == int(n['NewBrdLotQty']):
        pop['lot_agree'] += 1
    else:
        pop['lot_disagree'] += 1
    try:
        lo, hi = n['PricRg'].split('-')
        t = Decimal(int(n['BidIntrvl'])) / 100
        if t > 0:
            pop['band_multiple_of_tick' if (Decimal(lo) % t == 0 and Decimal(hi) % t == 0) else 'band_not_multiple'] += 1
    except Exception:
        pop['band_unparsed'] += 1
res['population_crosscheck_all_EQ'] = dict(pop)
res['nse_bidintrvl_values_EQ'] = collections.Counter(r['BidIntrvl'] for r in nse if r['SctySrs'] == 'EQ').most_common()

# ---- E in-file TRAIN evidence
ue = [int(r['UpdDt']) for r in nse if r['UpdDt'].strip().isdigit()]
res['nse_UpdDt_max_1980epoch'] = (E80 + datetime.timedelta(seconds=max(ue))).isoformat()
res['nse_UpdDt_max_if_unix_epoch'] = (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=max(ue))).isoformat()
tcols = ['tradingsymbol', 'isin', 'nse_FinInstrmId', 'nse_ListgDt', 'nse_IsseDt', 'listed_before_TRAIN_start', 'nse_RmvlDt', 'nse_RadmssnDt',
         'nse_DelFlg', 'nse_SctyStsNrmlMkt', 'nse_ElgbltyNrmlMkt', 'nse_ParVal', 'nse_AddtlInf', 'nse_UpdDt_utcnaive', 'nse_RcrdDt', 'nse_SpclExDt']
trows = []
post = []
for s in syms:
    n = nse_eq[s][0]
    ld = nse_date(n['ListgDt'])
    before = bool(ld) and datetime.date.fromisoformat(ld) < TRAIN_START
    if not before:
        post.append((s, ld))
    trows.append(dict(
        tradingsymbol=s, isin=n['ISIN'], nse_FinInstrmId=n['FinInstrmId'], nse_ListgDt=ld, nse_IsseDt=nse_date(n['IsseDt']),
        listed_before_TRAIN_start='TRUE' if before else 'FALSE', nse_RmvlDt=nse_date(n['RmvlDt']), nse_RadmssnDt=nse_date(n['RadmssnDt']),
        nse_DelFlg=n['DelFlg'], nse_SctyStsNrmlMkt=n['SctyStsNrmlMkt'], nse_ElgbltyNrmlMkt=n['ElgbltyNrmlMkt'], nse_ParVal=n['ParVal'],
        nse_AddtlInf=n['AddtlInf'], nse_UpdDt_utcnaive=(E80 + datetime.timedelta(seconds=int(n['UpdDt']))).strftime('%Y-%m-%d %H:%M:%S'),
        nse_RcrdDt=nse_date(n['RcrdDt']), nse_SpclExDt=nse_date(n['SpclExDt'])))
with open(os.path.join(OUT, 'TRAIN_INFILE_EVIDENCE.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=tcols, lineterminator='\n')
    w.writeheader()
    w.writerows(trows)
res['not_listed_before_TRAIN_start'] = post
res['addtl_inf_48'] = collections.Counter(r['nse_AddtlInf'] for r in trows).most_common()
res['listing_range_48'] = [min(r['nse_ListgDt'] for r in trows), max(r['nse_ListgDt'] for r in trows)]
res['latest_listing_48'] = sorted(((r['nse_ListgDt'], r['tradingsymbol']) for r in trows))[-4:]
res['rcrd_or_spclex_in_train_window'] = [
    (r['tradingsymbol'], r['nse_RcrdDt'], r['nse_SpclExDt']) for r in trows
    if any(x and TRAIN_START <= datetime.date.fromisoformat(x) < TRAIN_END_EXCL for x in (r['nse_RcrdDt'], r['nse_SpclExDt']))]
res['kite_dump_has_listing_or_status_fields'] = [c for c in kite[0].keys() if c in ('listing_date', 'status', 'isin')]

json.dump(res, open(os.path.join(OUT, 'analysis_results.json'), 'w'), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
