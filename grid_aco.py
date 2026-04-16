"""Grid search cycle-aware ACO params."""
import subprocess
import re
import shutil

TEMPLATE = open("round1.py").read()

configs = []
for cw in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]:
    for rc in [0.0, 0.1, 0.2, 0.3, 0.5]:
        for cs_thresh in [0.3, 0.5, 1.0]:
            configs.append((cw, rc, cs_thresh))

print(f"Testing {len(configs)} configs...")
results = []

for i, (cw, rc, cs_thresh) in enumerate(configs):
    code = TEMPLATE
    code = code.replace("OSMIUM_CYCLE_WEIGHT = 1.5", f"OSMIUM_CYCLE_WEIGHT = {cw}")
    code = code.replace("OSMIUM_REVERSION_COEFF = 0.3", f"OSMIUM_REVERSION_COEFF = {rc}")
    code = code.replace("if cycle_signal > 0.5:", f"if cycle_signal > {cs_thresh}:")
    code = code.replace("elif cycle_signal < -0.5:", f"elif cycle_signal < -{cs_thresh}:")

    test_path = "/Users/rohan/prosperity4/aco_test.py"
    with open(test_path, "w") as f:
        f.write(code)

    try:
        out = subprocess.run(
            ["prosperity4btx", "aco_test.py", "1"],
            capture_output=True, text=True, timeout=60,
            cwd="/Users/rohan/prosperity4"
        )
        # Extract per-day ACO profits
        aco_totals = re.findall(r"ASH_COATED_OSMIUM:\s+([\d,]+)", out.stdout)
        ipr_totals = re.findall(r"INTARIAN_PEPPER_ROOT:\s+([\d,]+)", out.stdout)
        total_match = re.findall(r"Total profit:\s+([\d,]+)", out.stdout)

        aco_sum = sum(int(x.replace(",", "")) for x in aco_totals)
        total = sum(int(x.replace(",", "")) for x in total_match[-3:]) if len(total_match) >= 3 else 0

        results.append((cw, rc, cs_thresh, aco_sum, total))
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(configs)} done...")
    except Exception as e:
        results.append((cw, rc, cs_thresh, 0, 0))

# Sort by ACO profit
results.sort(key=lambda x: -x[3])
print(f"\n{'CycleWt':>8} {'RevCoef':>8} {'CSThres':>8} {'ACO PnL':>10} {'Total PnL':>12}")
print("-" * 55)
for cw, rc, cs, aco, total in results[:20]:
    print(f"{cw:>8.1f} {rc:>8.1f} {cs:>8.1f} {aco:>10,} {total:>12,}")

print("\n\nBaseline (no signals): cw=0.0, rc=0.0")
baseline = [r for r in results if r[0] == 0.0 and r[1] == 0.0]
if baseline:
    print(f"  ACO={baseline[0][3]:,}, Total={baseline[0][4]:,}")
