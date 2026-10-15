"""Mutation check for the isolated integration (SYNTHETIC tests only): each mutant is applied to a COPY of harness/ and
test_isolated_integration.py must FAIL. The real harness/ is never modified. Usage: python -I mutation_integration.py [name ...]"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
MUTANTS = {
    "release_skips_external_pin": ("release_record.py", "if actual != external_pin:", "if False:"),
    "release_accepts_untrusted_issuer": ("release_record.py", "if not scopes or scope not in scopes:", "if False:"),
    "release_real_scope_not_closed": ("release_record.py", "if not REAL_TRUSTED_ISSUERS or rec[\"issuer\"] not in REAL_TRUSTED_ISSUERS or _real_pin() != actual:", "if False:"),
    "release_skips_classification_scope": ("release_record.py", "if SCOPE_FOR_CLASSIFICATION.get(rec[\"classification\"]) != scope:", "if False:"),
    "release_skips_pin_equality": ("release_record.py", "if pins != dict(expected[key]):", "if False:"),
    "release_skips_binding_equality": ("release_record.py", "if rec[key] != expected[key]:", "if False:"),
    "auth_skips_bijection": ("curated_artifact.py", "if stock != set(stock_symbols) or grid != set(grid_feeds):", "if False:"),
    "auth_skips_sha_pin": ("curated_artifact.py", "if actual_sha != authorization_sha256_pin:", "if False:"),
    "auth_ignores_eof_flag": ("curated_artifact.py", "if entry[\"ends_at_eof\"] is not True:", "if False:"),
    "auth_skips_train_boundaries": ("curated_artifact.py", "if train[\"train_start\"] != periods[\"train_start\"] or train[\"train_end_exclusive\"] != periods[\"train_end_exclusive\"]:", "if False:"),
    "loader_skips_row_count": ("curated_artifact.py", "if data_rows != art.row_count:", "if False:"),
    "loader_skips_extent": ("curated_artifact.py", "if first_raw != art.first_timestamp or last_raw != art.last_timestamp:", "if False:"),
    "loader_skips_train_end": ("curated_artifact.py", "            if day >= end_date:\n                raise h.ChronologyError(f\"{art.alias}: row", "            if False:\n                raise h.ChronologyError(f\"{art.alias}: row"),
    "loader_allows_rows_after_block": ("curated_artifact.py", "            if day > last_date:\n                raise CuratedArtifactError", "            if False:\n                raise CuratedArtifactError"),
    "loader_drops_commitment": ("curated_artifact.py", "max_physical_bytes=art.size_bytes + 1,\n                               expected_commitment=art.sha256)", "max_physical_bytes=art.size_bytes + 1,\n                               expected_commitment=None)"),
    "loader_skips_size_check": ("curated_artifact.py", "if os.stat(path).st_size != art.size_bytes:\n        raise CuratedArtifactError(f\"{art.alias}: size differs", "if False:\n        raise CuratedArtifactError(f\"{art.alias}: size differs"),
    "loader_skips_pretrain_policy": ("curated_artifact.py", "if pretrain_policy != \"WARMUP_PROVENANCE_NO_FIT\":\n                    raise h.PreTrainSelectionError(f\"{art.alias}: preTRAIN row {day} present", "if False:\n                    raise h.PreTrainSelectionError(f\"{art.alias}: preTRAIN row {day} present"),
    "grid_skips_train_end": ("curated_artifact.py", "if local >= end_date:", "if False:"),
    "source_audit_noop": ("curated_artifact.py", "    if bad_path or bad_modules:\n        raise SourceRootEscape", "    if False:\n        raise SourceRootEscape"),
    "target_skips_release": ("curated_target.py", "    grant = rr.validate_release_record(", "    grant = rr.ReleaseGrant(scope='SYNTHETIC_ONLY', record_id='x', issuer='x', record_sha256='0'*64, classification=plan.classification, execution_id=plan.execution_id, authorization_sha256=plan.authorization_sha256) if True else rr.validate_release_record("),
    "target_skips_witness": ("curated_target.py", "    witness = osi.active_witness()\n    verified", "    witness = dict(osi._ACTIVE['witness']) if osi._ACTIVE else dict(profile=osi.PROFILE, verified_input_sha256={}, verified_code_pins={}, runtime_dirs=[])\n    verified"),
    "target_skips_metadata_sha": ("curated_target.py", "if verified.get(alias) != _sha(data):", "if False:"),
    "target_tolerates_any_fd_violation": ("curated_target.py", "    if rest:\n        raise osi.WitnessError", "    if False:\n        raise osi.WitnessError"),
    "target_skips_inventory": ("curated_target.py", "if set(verified) != set(ca.META_ALIASES.values()) | set(plan.artifacts):", "if False:"),
    "launcher_skips_host_release": ("curated_launcher.py", "    grant = rr.validate_release_record(meta[\"release_record\"], external_pin=cfg[\"release_record_sha256\"],\n                                       trusted_issuers=cfg[\"trusted_issuers\"], expected=expected)", "    grant = rr.ReleaseGrant('SYNTHETIC_ONLY', 'x', 'x', '0'*64, plan.classification, plan.execution_id, plan.authorization_sha256)"),
    "launcher_skips_alias_check": ("curated_launcher.py", "if set(cfg[\"artifacts\"]) != set(plan.artifacts):", "if False:"),
}


def main(names):
    todo = names or sorted(MUTANTS)
    survivors, log = [], []
    for name in todo:
        fname, old, new = MUTANTS[name]
        work = Path(tempfile.mkdtemp(prefix="mut_", dir=P / "test_tmp"))
        mut = work / "harness"
        shutil.copytree(P / "harness", mut, ignore=shutil.ignore_patterns("__pycache__"))
        text = (mut / fname).read_text()
        if text.count(old) != 1:
            log.append(f"{name}: SETUP-ERROR pattern count {text.count(old)}")
            survivors.append(name)
            continue
        (mut / fname).write_text(text.replace(old, new))
        env = dict(os.environ, WP004_INTEGRATION_HARNESS_DIR=str(mut))
        r = subprocess.run([PY, "-I", "-m", "pytest", str(P / "harness_tests/test_isolated_integration.py"), "-x", "-q", "-W", "ignore",
                            "-p", "no:cacheprovider", "--basetemp", str(work / "bt"), "--tb=line"],
                           capture_output=True, text=True, env=env, timeout=900)
        tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or " passed" in ln or " failed" in ln]
        killed = r.returncode != 0
        log.append(f"{name}: {'KILLED' if killed else 'SURVIVED'}  {tail[:2]}")
        print(log[-1], flush=True)
        if not killed:
            survivors.append(name)
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{len(todo) - len(survivors)}/{len(todo)} mutants KILLED; survivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
