"""The parameter register is the single source of counts; the audit summary is generated from it."""
import json
from pathlib import Path

import pytest

from scripts import r5_parameter_register as reg

ROOT = Path(__file__).resolve().parents[1] / "docs" / "r5_remediation_project"
REGISTER, AUDIT = ROOT / "R5_PARAMETER_REGISTER.json", ROOT / "R5_PARAMETER_PROVENANCE_AUDIT.md"


def test_committed_register_is_valid_and_counts_sum_to_total():
    register = reg.load(REGISTER)
    total, by_class = reg.counts(register)
    assert total == len(register["parameters"]) == sum(by_class.values())
    assert len({r["id"] for r in register["parameters"]}) == total


def test_committed_audit_summary_matches_the_register():
    assert reg.main([str(REGISTER), str(AUDIT), "--check"]) == 0


def test_duplicate_ids_invalid_class_and_missing_fields_are_rejected(tmp_path):
    row = dict(id="X-1", parameter="p", classification="A", file="f.py")
    for rows, message in (([row, dict(row)], "duplicate"), ([dict(row, classification="Z")], "invalid classification"),
                          ([{k: v for k, v in row.items() if k != "file"}], "lacks")):
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"parameters": rows}))
        with pytest.raises(ValueError, match=message):
            reg.load(path)


def test_a_stale_audit_summary_fails_the_check(tmp_path):
    path, audit = tmp_path / "r.json", tmp_path / "a.md"
    path.write_text(json.dumps({"parameters": [dict(id="X-1", parameter="p", classification="J", file="f.py")]}))
    reg.main([str(path), str(audit), "--write"])
    assert reg.main([str(path), str(audit), "--check"]) == 0
    audit.write_text(audit.read_text().replace("J=1", "J=0"))
    assert reg.main([str(path), str(audit), "--check"]) == 1


def test_every_original_hij_row_has_one_closure_record_and_isolated_rows_name_their_evidence():
    import csv
    register = reg.load(REGISTER)
    assert register["original_hij_counts"] == {"H": 28, "I": 30, "J": 4}
    originals = [r for r in register["parameters"] if r.get("original_class")]
    assert len(originals) == 62
    with open(ROOT / "R5_FINAL_PARAMETER_CLOSURE.csv", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert [r["ID"] for r in table] == [r["id"] for r in originals]
    for original in ("H", "I", "J"):
        assert sum(r["ORIGINAL_CLASS"] == original for r in table) == register["original_hij_counts"][original]
    for row in originals:
        assert row["runtime_reachability"] and row["blocker_class"] and row["closed"] in ("YES", "NO") and row["closure_reason"]
        if row["closed"] == "YES":
            assert row["closure_test"] != "none", row["id"]                        # a closed row must name its test
        if row["active_in_production"] == "NO":
            assert row["final_state"] in ("P4", "P2") and row["closure_test"] != "none"   # isolation claims name their evidence


def test_active_unresolved_rows_are_counted_not_hidden():
    register = reg.load(REGISTER)
    active, simulation, live_only, p0, p1 = reg.activity(register)
    unresolved = [r for r in register["parameters"] if r.get("closed") == "NO"]
    assert sum(active.values()) == len(unresolved) == 34 and p0 == 0
    assert all(r["active_in_production"] == "YES" for r in unresolved)
