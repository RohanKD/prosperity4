"""
Run all strategy variants against 99362 baseline and report per-product results.
Usage: python test_variants.py
"""
import subprocess, shutil, re, os

TRADER = "C:/Users/kevin/stuff/prosperity4/trader.py"
BASE = "C:/Users/kevin/stuff/prosperity4/99362.py"

def run_backtest():
    result = subprocess.run(
        ["prosperity4btx", "trader.py", "0"],
        cwd="C:/Users/kevin/stuff/prosperity4",
        capture_output=True, text=True
    )
    out = result.stdout + result.stderr
    # Parse per-product per-day — collect ALL days, use last total seen
    days = {}
    current_day = None
    last_total = 0
    for line in out.split("\n"):
        m = re.match(r"Backtesting .* on round 0 day ([-\d]+)", line)
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
    em_total = sum(d.get("EMERALDS", 0) for d in days.values())
    tom_total = sum(d.get("TOMATOES", 0) for d in days.values())
    print(f"{label:<45} EM={em_total:>7,}  TOM={tom_total:>7,}  TOTAL={total:>8,}")
    return {"emeralds": em_total, "tomatoes": tom_total, "total": total}

# ── Variant files ──────────────────────────────────────────────────────────
VARIANTS_DIR = "C:/Users/kevin/stuff/prosperity4/variants"
os.makedirs(VARIANTS_DIR, exist_ok=True)

results = {}
print(f"\n{'Label':<45} {'EMERALDS':>10}  {'TOMATOES':>10}  {'TOTAL':>10}")
print("-" * 80)

# Baseline
shutil.copy(BASE, f"{VARIANTS_DIR}/baseline.py")
results["baseline"] = test("BASELINE (99362)", f"{VARIANTS_DIR}/baseline.py")

# Load variant files
for fname in sorted(os.listdir(VARIANTS_DIR)):
    if fname == "baseline.py":
        continue
    if fname.endswith(".py"):
        label = fname.replace(".py", "")
        path = f"{VARIANTS_DIR}/{fname}"
        results[label] = test(label, path)

# Restore baseline
shutil.copy(BASE, TRADER)
print("\nDone. trader.py restored to 99362 baseline.")
print(f"\n{'Label':<45} {'vs baseline':>12}")
print("-" * 60)
base_total = results["baseline"]["total"]
for label, r in sorted(results.items(), key=lambda x: -x[1]["total"]):
    diff = r["total"] - base_total
    sign = "+" if diff >= 0 else ""
    marker = " <-- BEST" if diff == max(r2["total"]-base_total for r2 in results.values()) and diff > 0 else ""
    print(f"  {label:<43} {sign}{diff:>+,}{marker}")
