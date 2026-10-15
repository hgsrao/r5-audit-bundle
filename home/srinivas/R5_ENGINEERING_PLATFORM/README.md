# R5 Engineering Platform

Repository organization normalized under WP-EOS-001. The frozen Engineering
Bridge 1.2 source, tests, examples and configuration remain byte-identical.

## Locations

| Content | Location |
|---|---|
| Engineering constitution and standards | architecture/ |
| Bridge routing diagram | architecture/bridge/ROUTING.md |
| Frozen bridge source | bridge/src/ |
| Bridge tests | bridge/tests/ |
| Bridge request/response examples | bridge/examples/ |
| Bridge runtime configuration | bridge/src/config.py |
| Bridge packaging/test/lint settings | bridge/pyproject.toml |
| Bridge documentation and usage | bridge/README.md |
| Bridge runtime responses/logs | bridge/work/ and bridge/logs/ |
| Knowledge and research scaffolds | knowledge_base/ |
| Historical bridge acceptance/test/build reports | reports/bridge/ |
| Historical freeze/source receipts | receipts/bridge/ |
| Release distributions | outputs/bridge/releases/ |
| Preserved generated/temporary snapshots | outputs/bridge/generated_snapshot/ and outputs/bridge/temporary_snapshot/ |
| Normalization inventory and reports | reports/eos001/ |
| Normalization identity receipt | receipts/eos001/normalization_identity.json |

Bridge-specific examples/configuration remain with the bridge because existing
imports, tests and operational settings depend on that layout. Runtime work/log
paths are preserved. No source, test, parameter, formula or architectural policy
was rewritten.

Canonical empty engineering folders remain for config, docs, audits, scripts,
tests, logs and receipt categories. Unused empty legacy scaffolds were removed;
the exact paths are in reports/eos001/empty_directories_removed.json. No file was
deleted. Equal-content files are preserved and listed, rather than deduplicated.

## Bridge verification and use

From bridge/, use the accepted commands:

```sh
python -m pytest -q -W error
ruff check src tests
python -m py_compile src/*.py
```

Use a configured Python 3.12+ environment. See bridge/README.md for the existing
communication interface. Tests mock external calls. No network call is needed
for verification. Build artifacts should be directed to outputs/, with a scratch
checkout used when build tooling generates intermediate files.

Historical receipts describe paths at their original release. Resolve their old
locations with reports/eos001/migration_table.csv; the original freeze receipt
has not been rewritten. It binds the original README, while the normalization
receipt separately records the authorized reference-only README repair.

Normalization does not initialize Git or change trading repositories. Empty ADR
files remain placeholders, not completed architectural decisions. New engineering
work is outside WP-EOS-001.
