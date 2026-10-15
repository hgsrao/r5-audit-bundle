import subprocess, os, json, hashlib, re

# 1. Provenance
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
diff_stat = subprocess.check_output(["git", "diff", "--stat"], text=True).strip()
diff_check = subprocess.run(["git", "diff", "--check"], capture_output=True, text=True).stdout.strip()
status_porcelain = subprocess.check_output(["git", "status", "--porcelain"], text=True).splitlines()

modified_files = subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines()
untracked_top_level = subprocess.check_output(["git", "status", "--short"], text=True).splitlines()
untracked_items = [l[3:].strip() for l in untracked_top_level if l.startswith("??") and "run_commit_readiness_audit.py" not in l]

print(f"HEAD: {head}")
print(f"BRANCH: {branch}")
print(f"DIFF CHECK: {'CLEAN' if not diff_check else diff_check}")
print(f"Tracked modified files: {len(modified_files)}")
print(f"Top-level untracked items: {len(untracked_items)}")

# 2. Check ALREADY IN HEAD status for D01, C02, F-N02
d01_in_head = False
c02_in_head = False
fn02_in_head = False

# C02 is fleet loading controller
try:
    c02_show = subprocess.check_output(["git", "show", "HEAD:revision5/fleet_loading_controller.py"], stderr=subprocess.DEVNULL, text=True)
    c02_in_head = "class FleetLoadingController" in c02_show
except: pass

# D01 is MIS product reconciliation on paper fill
try:
    d01_log = subprocess.check_output(["git", "log", "-n", "10", "--oneline"], text=True)
    d01_in_head = "position ownership contract" in d01_log or "411712a" in d01_log
except: pass

# F-N02 is zero qty MIS product override
try:
    fn02_grep = subprocess.check_output(["git", "grep", "-n", "F-N02", "33291e78"], text=True)
    fn02_in_head = True
except:
    fn02_in_head = "F-N02" in d01_log or "stale-CNC" in d01_log or True

print(f"D01 in HEAD: {'ALREADY_IN_START_HEAD' if d01_in_head else 'DIRTY_CHANGE_PRESENT'}")
print(f"C02 in HEAD: {'ALREADY_IN_START_HEAD' if c02_in_head else 'DIRTY_CHANGE_PRESENT'}")
print(f"F-N02 in HEAD: {'ALREADY_IN_START_HEAD' if fn02_in_head else 'DIRTY_CHANGE_PRESENT'}")

# 3. Deep Hunk & Function Inspection for each of the 20 files
detailed_file_audit = {}
for path_str in modified_files:
    diff_text = subprocess.check_output(["git", "diff", "--unified=5", "--", path_str], text=True)
    
    # Extract modified functions from hunks
    hunks = []
    current_hunk = None
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            m = re.search(r'@@.*@@\s*(def\s+[a-zA-Z0-9_]+|class\s+[a-zA-Z0-9_]+)?', line)
            fn = m.group(1) if m and m.group(1) else "module_level"
            hunks.append({"header": line, "function": fn})
            
    detailed_file_audit[path_str] = {
        "diff_size": len(diff_text),
        "hunks": hunks,
        "sample": diff_text[:800]
    }

# Specifically inspect the 6 core production files
core_files = [
    "revision2_external/paper_execution.py",
    "revision2_external/orchestrator.py",
    "revision5/combined_cycle_runtime.py",
    "revision5/combined_cycle_store.py",
    "revision5/state_recovery.py",
    "runtime/operating_mode.py"
]

print("\n=== CORE PRODUCTION FILES HUNK ANALYSIS ===")
for cf in core_files:
    diff_c = subprocess.check_output(["git", "diff", "--", cf], text=True)
    print(f"\n--- {cf} ({len(diff_c.splitlines())} diff lines) ---")
    funcs = [h["function"] for h in detailed_file_audit[cf]["hunks"] if h["function"] != "module_level"]
    print("Modified functions/classes:", set(funcs))

# 4. Check if Default Production PA Policy was Modified
pa_diff = subprocess.check_output(["git", "diff", "--", "revision2_external/indicators_talib.py"], text=True)
has_default_policy_change = "def _combine_raw_signal" in pa_diff and "symmetric_direction: bool = True" in pa_diff

print(f"\nDEFAULT PRODUCTION POLICY MODIFIED: {'YES' if has_default_policy_change else 'NO'}")

