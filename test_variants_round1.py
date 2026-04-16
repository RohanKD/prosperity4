"""
Run all round1 strategy variants and report per-product results.
Usage: python test_variants_round1.py
"""
import subprocess, shutil, re, os

TRADER = "C:/Users/kevin/stuff/prosperity4/trader.py"
BASE = "C:/Users/kevin/stuff/prosperity4/round1.py"
VARIANTS_DIR = "C:/Users/kevin/stuff/prosperity4/variants_round1"

def run_backtest():
    result = subprocess.run(
        ["prosperity4btx", "trader.py", "1", "--data", "./data"],
        cwd="C:/Users/kevin/stuff/prosperity4",
        capture_output=True, text=True
    )
    out = result.stdout + result.stderr
    days = {}
    current_day = None
    last_total = 0
    for line in out.split("\n"):
        m = re.match(r"Backtesting .* on round 1 day ([-\d]+)", line)
        if m:
            current_day = int(m.group(1))
            days[current_day] = {}
        m2 = re.match(r"(\w+): ([\d,]+)", line.strip())
        if m2 and current_day is not None and m2.group(1) not in ("Total",):
            days[current_day][m2.group(1)] = int(m2.group(2).replace(",", ""))
        m3 = re.match(r"Total profit: ([\d,]+)", line.strip())
        if m3:
            last_total = int(m3.group(1).replace(",", ""))
    return days, last_total

def test(label, variant_file):
    shutil.copy(variant_file, TRADER)
    days, total = run_backtest()
    pepper_total = sum(d.get("INTARIAN_PEPPER_ROOT", 0) for d in days.values())
    osmium_total = sum(d.get("ASH_COATED_OSMIUM", 0) for d in days.values())
    print(f"{label:<45} PEPPER={pepper_total:>8,}  OSMIUM={osmium_total:>7,}  TOTAL={total:>9,}")
    return {"pepper": pepper_total, "osmium": osmium_total, "total": total}

os.makedirs(VARIANTS_DIR, exist_ok=True)

results = {}
print(f"\n{'Label':<45} {'PEPPER':>10}  {'OSMIUM':>9}  {'TOTAL':>11}")
print("-" * 85)

# Baseline
results["baseline"] = test("BASELINE (round1)", BASE)

# Variants
for fname in sorted(os.listdir(VARIANTS_DIR)):
    if fname.endswith(".py"):
        label = fname.replace(".py", "")
        path = f"{VARIANTS_DIR}/{fname}"
        results[label] = test(label, path)

# Restore baseline
shutil.copy(BASE, TRADER)
print("\nDone. trader.py restored to round1 baseline.")
print(f"\n{'Label':<45} {'vs baseline':>12}")
print("-" * 60)
base_total = results["baseline"]["total"]
for label, r in sorted(results.items(), key=lambda x: -x[1]["total"]):
    diff = r["total"] - base_total
    sign = "+" if diff >= 0 else ""
    best_diff = max(r2["total"] - base_total for r2 in results.values())
    marker = " <-- BEST" if diff == best_diff and diff > 0 else ""
    print(f"  {label:<43} {sign}{diff:>+,}{marker}")
