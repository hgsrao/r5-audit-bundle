"""Validate the R5 parameter register and generate the audit summary from it (no hand-kept counts).

    python scripts/r5_parameter_register.py REGISTER.json AUDIT.md --write   # regenerate the summary block
    python scripts/r5_parameter_register.py REGISTER.json AUDIT.md --check   # fail if the audit disagrees with the register
"""
import argparse
import collections
import json
import sys
from pathlib import Path

CLASSES = ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J')
MEANING = dict(A='physical / mathematical', B='external rule', C='approved risk policy', D='data-derived dynamic',
               E='model-calibrated', F='operating configuration', G='test-only', H='UNJUSTIFIED_MAGIC',
               I='PLACEHOLDER', J='UNKNOWN')
REQUIRED = ('id', 'parameter', 'classification', 'file')
BEGIN, END = '<!-- REGISTER_SUMMARY_BEGIN -->', '<!-- REGISTER_SUMMARY_END -->'


def load(path):
    register = json.loads(Path(path).read_text())
    rows = register.get('parameters')
    if not isinstance(rows, list) or not rows:
        raise ValueError('register has no parameter rows')
    for row in rows:
        missing = [k for k in REQUIRED if not row.get(k)]
        if missing:
            raise ValueError(f"row {row.get('id')!r} lacks {missing}")
        if row['classification'] not in CLASSES:
            raise ValueError(f"row {row['id']!r} has invalid classification {row['classification']!r}")
    duplicates = [k for k, n in collections.Counter(r['id'] for r in rows).items() if n > 1]
    if duplicates:
        raise ValueError(f'duplicate parameter ids: {duplicates}')
    return register


def counts(register):
    rows = register['parameters']
    tally = collections.Counter(r['classification'] for r in rows)
    result = {c: tally.get(c, 0) for c in CLASSES}
    if sum(result.values()) != len(rows):
        raise ValueError('classification counts do not sum to the row count')
    return len(rows), result


def blockers(register):
    """H/I/J rows grouped by qualification (rows without one are reported as UNREVIEWED)."""
    grouped = collections.Counter()
    for row in register['parameters']:
        if row['classification'] in ('H', 'I', 'J'):
            grouped[(row['classification'], row.get('qualification', 'UNREVIEWED'))] += 1
    return grouped


def activity(register):
    """ACTIVE_* = still-unresolved H/I/J rows that can influence production decisions; SIMULATION_ONLY_* = H/I/J rows that are
    isolated (active_in_production == NO).  Rows without the IR-02 fields are conservatively counted ACTIVE."""
    active, simulation, live_only = collections.Counter(), collections.Counter(), 0
    p0 = p1 = 0
    for row in register['parameters']:
        letter = row['classification']
        if letter not in ('H', 'I', 'J'):
            continue
        if row.get('active_in_production', 'YES') == 'NO':
            simulation[letter] += 1
            live_only += row.get('runtime_reachability') == 'LIVE_ONLY_DISCONNECTED'
        else:
            active[letter] += 1
            blocker = row.get('blocker_class', '')
            p0 += blocker.startswith('P0')
            p1 += blocker.startswith('P1')
    return active, simulation, live_only, p0, p1


def summary(register):
    total, by_class = counts(register)
    grouped = blockers(register)
    active, simulation, live_only, p0, p1 = activity(register)
    lines = [BEGIN, f'TOTAL_ROWS={total}', *[f'{c}={by_class[c]}' for c in CLASSES],
             'DUPLICATE_PARAMETER_IDS=0', '', '| Class | Meaning | Count |', '|---|---|---|',
             *[f'| {c} | {MEANING[c]} | {by_class[c]} |' for c in CLASSES], '',
             '| H/I/J class | Qualification | Rows |', '|---|---|---|',
             *[f'| {c} | {q} | {n} |' for (c, q), n in sorted(grouped.items())],
             f'MATERIAL_UNJUSTIFIED_MAGIC={by_class["H"]}', f'MATERIAL_PLACEHOLDERS={by_class["I"]}',
             f'MATERIAL_UNKNOWN_PROVENANCE={by_class["J"]}', '',
             *[f'ACTIVE_{c}={active[c]}' for c in 'HIJ'], *[f'SIMULATION_ONLY_{c}={simulation[c]}' for c in 'HIJ'],
             f'LIVE_ONLY_UNQUALIFIED={live_only}', f'P0_REMAINING={p0}', f'P1_REMAINING={p1}', END]
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('register')
    parser.add_argument('audit')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    block = summary(load(args.register))
    audit = Path(args.audit)
    text = audit.read_text() if audit.exists() else ''
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        updated = head + block + tail
    else:
        updated = text + ('\n' if text else '') + block + '\n'
    if args.check:
        if updated != text:
            print('audit summary disagrees with the register', file=sys.stderr)
            return 1
        return 0
    audit.write_text(updated)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
