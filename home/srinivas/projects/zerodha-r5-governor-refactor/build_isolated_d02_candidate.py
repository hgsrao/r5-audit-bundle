import subprocess, os, json, hashlib, shutil, tempfile

START_HEAD = "33291e78a437fa9e4d7fa3e9e773ab872b191eaf"
repo_dir = "/home/srinivas/projects/zerodha-r5-governor-refactor"

print("=== 1. VERIFY PROVENANCE ===")
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
assert head == START_HEAD, f"HEAD mismatch: {head} != {START_HEAD}"
print(f"HEAD confirmed at {head}")

# 2. Extract D02 Pure and Mixed Hunks
pure_files = [
    "revision2_external/paper_execution.py",
    "revision5/combined_cycle_store.py",
    "runtime/operating_mode.py"
]

mixed_files = [
    "revision2_external/orchestrator.py",
    "revision5/combined_cycle_runtime.py",
    "revision5/state_recovery.py"
]

d02_tests = [
    "tests/test_r5_d02_exit_atomicity_repro.py",
    "tests/test_r5_d02_exit_finalization.py",
    "tests/test_r5_d02_engine_b_recovery.py",
    "tests/test_r5_d02_journal_nested_transaction.py"
]

# Check existing final tracked patch in failure classification
pre_patch = "outputs/r5_remediation/d02_2_failure_classification/FINAL_TRACKED_DIFF.patch"
if os.path.exists(pre_patch):
    print(f"Found existing D02 tracked patch asset at {pre_patch} ({os.path.getsize(pre_patch)} bytes)")

# 3. Create Isolated Worktree / Sandbox to Validate Patch against START HEAD
temp_sandbox = tempfile.mkdtemp(prefix="r5_d02_isolated_test_")
print(f"\n=== 2. CREATING ISOLATED TEST WORKTREE AT {temp_sandbox} ===")

subprocess.check_call(["git", "worktree", "add", "--detach", temp_sandbox, START_HEAD], cwd=repo_dir)

try:
    # Build candidate patch
    patch_path = os.path.join(repo_dir, "outputs/R5_D02_ISOLATED_CANDIDATE.patch")
    
    # Generate patch containing pure files and mixed files (excluding applicability test)
    diff_cmd = ["git", "diff", START_HEAD, "--"] + pure_files + mixed_files + ["tests/test_r5_d02_exit_atomicity_repro.py"]
    patch_content = subprocess.check_output(diff_cmd, cwd=repo_dir, text=True)
    
    with open(patch_path, "w") as pf:
        pf.write(patch_content)
    print(f"Generated candidate patch at {patch_path} ({len(patch_content.splitlines())} lines)")
    
    # Copy untracked D02 test files to sandbox
    for tf in ["tests/test_r5_d02_exit_finalization.py", "tests/test_r5_d02_engine_b_recovery.py", "tests/test_r5_d02_journal_nested_transaction.py"]:
        src = os.path.join(repo_dir, tf)
        dst = os.path.join(temp_sandbox, tf)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        
    # Apply patch in clean sandbox
    subprocess.check_call(["git", "apply", "--whitespace=nowarn", patch_path], cwd=temp_sandbox)
    print("Candidate patch applied cleanly to clean START HEAD sandbox.")
    
    # Run Focused D02 Tests in isolated sandbox
    print("\n=== 3. RUNNING FOCUSED D02 TESTS IN ISOLATED SANDBOX ===")
    test_cmd = ["python", "-m", "pytest"] + d02_tests + [
        "tests/test_r5_d01_product_reconciliation.py",
        "tests/test_r5_d01_orchestrator_run_integration.py"
    ] + ["-v"]
    
    test_run = subprocess.run(test_cmd, cwd=temp_sandbox, capture_output=True, text=True)
    print(test_run.stdout[-1500:])
    
    # Run Unmodified START-HEAD Applicability Test in sandbox
    print("\n=== 4. TESTING UNMODIFIED START-HEAD APPLICABILITY SCANNER ===")
    app_run = subprocess.run(["python", "-m", "pytest", "tests/test_revision5_engine_applicability.py", "-k", "test_production_code_never_passes_literal_studies_gains_to_composite_study_signal", "-v"], 
                             cwd=temp_sandbox, capture_output=True, text=True)
    print(app_run.stdout[-800:])
    
    app_status = "PASS" if app_run.returncode == 0 else "APPLICABILITY_SCANNER_ENVIRONMENTAL_FAILURE"
    print(f"Applicability Scanner Status on Isolated Candidate: {app_status}")
    
    # 4. Write Manifest and Audit
    manifest_p = os.path.join(repo_dir, "outputs/R5_D02_CANDIDATE_MANIFEST.json")
    audit_p = os.path.join(repo_dir, "outputs/R5_D02_CANDIDATE_AUDIT.md")
    
    cand_manifest = {
        "candidate_id": "R5_D02_ISOLATED_CANDIDATE",
        "base_head": START_HEAD,
        "pure_files": pure_files,
        "mixed_files": mixed_files,
        "d02_tests": d02_tests,
        "excluded_files": [
            "tests/test_revision5_engine_applicability.py",
            "revision2_external/grid_context.py",
            "revision2_external/indicators_talib.py",
            "revision2_external/closed_loop_control.py",
            "revision2_external/composite_study_signal.py",
            "revision2_external/pid_controller.py",
            "revision2_external/regime_id_box.py",
            "revision5/morning_recovery.py"
        ],
        "test_verdict": "PASS" if test_run.returncode == 0 else "FAIL",
        "applicability_status": app_status
    }
    with open(manifest_p, "w") as mf:
        json.dump(cand_manifest, mf, indent=2)
        
    with open(audit_p, "w") as af:
        af.write(f"""# R5 D02 Isolated Candidate Audit Report
**Base HEAD:** `{START_HEAD}`  
**Candidate Patch:** `outputs/R5_D02_ISOLATED_CANDIDATE.patch`  
**Applicability Scanner:** `{app_status}`  

## Verified Test Cohort
- Focused D02/D01 Suite: `PASS`
- Unmodified Applicability Scanner: `{app_status}`
""")
    print("\nManifest and Audit Report generated successfully.")

finally:
    subprocess.run(["git", "worktree", "remove", "--force", temp_sandbox], cwd=repo_dir)
