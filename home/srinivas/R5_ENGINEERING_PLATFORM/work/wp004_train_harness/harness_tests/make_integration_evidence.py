"""Evidence generator for WP-R5-004-ISOLATED-INTEGRATION (SYNTHETIC data only). Builds a synthetic world under
reports/.../isolated_integration/evidence, runs the ACTUAL launcher command (`python -I curated_launcher.py --config ...`) which
starts the target inside real bwrap, compares the sandbox outputs with the controlled baseline (original-source loaders on the
raw-like synthetic twin, host, unsandboxed), runs refusal samples, and records protected-tree fingerprints. Run with python -I."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/harness_tests")
import integration_world as iwm  # noqa: E402
import integration_fp  # noqa: E402
import test_isolated_integration as T  # noqa: E402

REPORT = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004/isolated_integration")
EV = REPORT / "evidence"
PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
LAUNCHER = iwm.PLATFORM / "harness" / "curated_launcher.py"


def run_cli(cfg_path):
    cmd = [PY, "-I", str(LAUNCHER), "--config", str(cfg_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    return dict(command=" ".join(cmd), returncode=r.returncode, stdout=r.stdout, stderr=r.stderr[-3000:])


def main():
    shutil.rmtree(EV, ignore_errors=True)
    EV.mkdir(parents=True)
    w = iwm.IntegrationWorld(EV / "world")
    cfg_path = EV / "launcher_config.json"
    cfg_path.write_text(json.dumps(w.cfg(), indent=2, sort_keys=True) + "\n")
    before = integration_fp.meta(iwm.PLATFORM / "snapshot")
    cli = run_cli(cfg_path)
    (EV / "LAUNCHER_RUN.json").write_text(json.dumps(cli, indent=2, sort_keys=True) + "\n")
    out = w.out_dir / "run"
    shutil.copytree(out, EV / "sandbox_output")      # first run, preserved before the reproducibility rerun
    receipt = json.loads((out / "curated_integration_receipt.json").read_text())
    # ---- reproducibility: second, separate launcher process on a fresh empty output dir
    first_hashes = T.file_hashes(out)
    first_fp = json.loads(cli["stdout"])["summary"]["block_fingerprint"]
    shutil.rmtree(out)
    cli2 = run_cli(cfg_path)
    repro = dict(first_block_fingerprint=first_fp, second_block_fingerprint=json.loads(cli2["stdout"])["summary"]["block_fingerprint"],
                 outputs_equal=first_hashes == T.file_hashes(out),
                 receipts_frame_fingerprints_equal=json.loads((EV / "sandbox_output" / "curated_integration_receipt.json").read_text())[
                     "frame_fingerprints"] == json.loads((out / "curated_integration_receipt.json").read_text())["frame_fingerprints"])
    repro["equal"] = repro["first_block_fingerprint"] == repro["second_block_fingerprint"] and repro["outputs_equal"]
    (EV / "REPRODUCIBILITY.json").write_text(json.dumps(repro, indent=2, sort_keys=True) + "\n")
    # ---- controlled baseline (host, unsandboxed, original-source loaders on the raw-like twin)
    run, ledger, ctx, root = T.curated_prepare(w)
    cur_out, ref_out = EV / "baseline_curated_host", EV / "baseline_original_source_host"
    res_cur = T.run_engine(lambda r_, p_, b_: run(), cur_out, w)
    res_ref = T.run_engine(lambda r_, p_, b_: (*T.reference_prepare(w), dict(slice_sha256="REFERENCE")), ref_out, w)
    cmp = dict(
        output_file_hashes=dict(sandbox=T.file_hashes(out), host_curated=T.file_hashes(cur_out), host_original_source=T.file_hashes(ref_out)),
        sandbox_equals_host_curated=T.file_hashes(out) == T.file_hashes(cur_out),
        sandbox_equals_original_source_baseline=T.file_hashes(out) == T.file_hashes(ref_out),
        block_fingerprint=dict(sandbox=receipt["block_fingerprint"], host_curated=res_cur["block_fingerprint"],
                               equal=receipt["block_fingerprint"] == res_cur["block_fingerprint"]),
        slice_sha256=dict(sandbox=receipt["slice_sha256"]),
        frame_fingerprints=dict(sandbox=receipt["frame_fingerprints"]),
        metrics_equal=res_cur["metrics"] == res_ref["metrics"],
        note="synthetic mechanics comparison only; 0 trades; no performance or candidate claim")
    (EV / "BASELINE_COMPARISON.json").write_text(json.dumps(cmp, indent=2, sort_keys=True) + "\n")
    # ---- refusal samples through the same CLI (no data opened, no sandbox started)
    refusals = {}
    for label, kw in (("wrong_release_pin", dict(pin_override="0" * 64)),
                      ("unknown_issuer", dict(trusted={"SOMEONE_ELSE": ["SYNTHETIC_ONLY"]})),
                      ("real_classification", dict(classification="NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC", data_origin="REAL_CURATED",
                                                   trusted={iwm.ISSUER: ["REAL_TRAIN_DIAGNOSTIC", "SYNTHETIC_ONLY"]}))):
        rw = iwm.IntegrationWorld(EV / f"refusal_{label}", **kw)
        p = EV / f"refusal_{label}" / "launcher_config.json"
        p.write_text(json.dumps(rw.cfg(), indent=2, sort_keys=True) + "\n")
        refusals[label] = run_cli(p)
        refusals[label]["output_dir_empty"] = not any(rw.out_dir.iterdir())
    (EV / "REFUSAL_SAMPLES.json").write_text(json.dumps(refusals, indent=2, sort_keys=True) + "\n")
    after = dict(snapshot=integration_fp.meta(iwm.PLATFORM / "snapshot"),
                 original_repo=integration_fp.meta("/home/srinivas/projects/zerodha-r5-governor-refactor"))
    pre = json.loads((REPORT / "PROTECTED_FINGERPRINT_BEFORE.json").read_text())
    (REPORT / "PROTECTED_FINGERPRINT_AFTER.json").write_text(json.dumps(dict(
        **after, snapshot_manifest_sha256=iwm.sha((iwm.PLATFORM / "SNAPSHOT_MANIFEST.json").read_bytes()),
        unchanged=dict(snapshot=after["snapshot"] == pre["snapshot"], original_repo=after["original_repo"] == pre["original_repo"],
                       snapshot_manifest=iwm.sha((iwm.PLATFORM / "SNAPSHOT_MANIFEST.json").read_bytes()) == pre["snapshot_manifest_sha256"])),
        indent=2, sort_keys=True) + "\n")
    print(json.dumps(dict(cli_rc=cli["returncode"], cli_stdout=cli["stdout"].strip(), equal_baseline=cmp["sandbox_equals_original_source_baseline"],
                          refusal_rcs={k: v["returncode"] for k, v in refusals.items()},
                          refusal_messages={k: v["stderr"].strip()[-200:] for k, v in refusals.items()}), indent=2))


if __name__ == "__main__":
    main()
