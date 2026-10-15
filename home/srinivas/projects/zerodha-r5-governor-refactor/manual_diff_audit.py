import subprocess, re, json, hashlib

# 1. Inspect HEAD for D01 and F-N02 in paper_execution.py
print("=== 1. D01 & F-N02 PROOF IN HEAD (33291e78) ===")
head_pe = subprocess.check_output(["git", "show", "33291e78:revision2_external/paper_execution.py"], text=True)
diff_pe = subprocess.check_output(["git", "diff", "--", "revision2_external/paper_execution.py"], text=True)

# Look for D01 MIS product assignment on fill
print("Checking HEAD for D01 MIS assignment:")
for line in head_pe.splitlines():
    if any(k in line for k in ["MIS", "CNC", "product ="]):
        print("  HEAD:", line.strip())

# Look for F-N02 stale CNC override
print("\nChecking diff of paper_execution.py (F-N02 / D02 additions):")
for line in diff_pe.splitlines():
    if any(k in line for k in ["product", "client_order_id", "stale", "CNC", "MIS", "+"]):
        if line.startswith("+") and not line.startswith("+++"):
            print("  DIFF +:", line.strip()[:100])

# Check C02 in HEAD
print("\n=== 2. C02 WIRING PROOF IN HEAD ===")
try:
    c02_grep = subprocess.check_output(["git", "grep", "-n", "FleetLoadingController", "33291e78"], text=True)
    print("FleetLoadingController wiring in HEAD:\n", c02_grep.strip()[:600])
except Exception as e:
    print("C02 grep error:", e)

# 3. Method-by-Method Diff for the Six Core D02 Files
core_files = [
    "revision2_external/paper_execution.py",
    "revision2_external/orchestrator.py",
    "revision5/combined_cycle_runtime.py",
    "revision5/combined_cycle_store.py",
    "revision5/state_recovery.py",
    "runtime/operating_mode.py"
]

print("\n=== 3. CORE D02 PRODUCTION FILES METHOD DIFFS ===")
for cf in core_files:
    diff_text = subprocess.check_output(["git", "diff", "--unified=1", "--", cf], text=True)
    print(f"\n>>> File: {cf} ({len(diff_text.splitlines())} diff lines)")
    hunks = re.findall(r'@@ [^@]+ @@\s*(def\s+[a-zA-Z0-9_]+|class\s+[a-zA-Z0-9_]+)?', diff_text)
    print("  Target functions/classes touched:", [h for h in hunks if h])

# 4. Other 7 Production Files Diff
other_files = [
    "revision2_external/closed_loop_control.py",
    "revision2_external/composite_study_signal.py",
    "revision2_external/grid_context.py",
    "revision2_external/indicators_talib.py",
    "revision2_external/pid_controller.py",
    "revision2_external/regime_id_box.py",
    "revision5/morning_recovery.py"
]

print("\n=== 4. OTHER PRODUCTION FILES DIFF AUDIT ===")
for of in other_files:
    diff_text = subprocess.check_output(["git", "diff", "--unified=1", "--", of], text=True)
    hunks = re.findall(r'@@ [^@]+ @@\s*(def\s+[a-zA-Z0-9_]+|class\s+[a-zA-Z0-9_]+)?', diff_text)
    print(f"{of} ({len(diff_text.splitlines())} lines):", [h for h in hunks if h])

# 5. Protected Inputs Verification
print("\n=== 5. PROTECTED INPUTS VERIFICATION ===")
inputs = {
    "trial_000.json": "/home/srinivas/projects/zerodha-phase1/outputs/r5_step5_stage_a_v2_state/params/trial_000.json",
    "sealed_protocol": "revision5/step5_sealed_calibration_protocol_v2.json",
    "baseline_ledger": "outputs/diagnostics/pa_gate_repair_block1/final/baseline/ledger.csv"
}

for name, path in inputs.items():
    if os.path.exists(path):
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        print(f"{name}: {h}")
    else:
        print(f"{name}: NOT_FOUND at {path}")

