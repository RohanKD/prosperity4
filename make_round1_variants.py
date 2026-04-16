"""Generate round1 variant files by patching specific parameter lines."""
import os, shutil, re

BASE = "C:/Users/kevin/stuff/prosperity4/round1.py"
OUT = "C:/Users/kevin/stuff/prosperity4/variants_round1"
os.makedirs(OUT, exist_ok=True)

base_text = open(BASE).read()

def make_variant(name, patches):
    """patches: list of (old_line_pattern, new_line) tuples."""
    text = base_text
    for old_pat, new_line in patches:
        text = re.sub(old_pat, new_line, text)
    path = f"{OUT}/{name}.py"
    with open(path, "w") as f:
        f.write(text)
    print(f"  created {name}.py")

# ── OSMIUM edge variants ───────────────────────────────────────────────────
make_variant("osmium_edge3", [
    (r"OSMIUM_DEFAULT_EDGE = \d+.*", "OSMIUM_DEFAULT_EDGE = 3        # was 5 — tighter spread"),
])
make_variant("osmium_edge4", [
    (r"OSMIUM_DEFAULT_EDGE = \d+.*", "OSMIUM_DEFAULT_EDGE = 4        # was 5 — tighter spread"),
])

# ── OSMIUM size variants ───────────────────────────────────────────────────
make_variant("osmium_size25", [
    (r"OSMIUM_BASE_SIZE = \d+.*", "OSMIUM_BASE_SIZE = 25           # was 20 — larger quotes"),
])
make_variant("osmium_size30", [
    (r"OSMIUM_BASE_SIZE = \d+.*", "OSMIUM_BASE_SIZE = 30           # was 20 — larger quotes"),
])

# ── OSMIUM combined variants ───────────────────────────────────────────────
make_variant("osmium_edge4_size25", [
    (r"OSMIUM_DEFAULT_EDGE = \d+.*", "OSMIUM_DEFAULT_EDGE = 4        # was 5"),
    (r"OSMIUM_BASE_SIZE = \d+.*",    "OSMIUM_BASE_SIZE = 25          # was 20"),
])
make_variant("osmium_edge3_size30", [
    (r"OSMIUM_DEFAULT_EDGE = \d+.*", "OSMIUM_DEFAULT_EDGE = 3        # was 5"),
    (r"OSMIUM_BASE_SIZE = \d+.*",    "OSMIUM_BASE_SIZE = 30          # was 20"),
])

# ── PEPPER variants ────────────────────────────────────────────────────────
make_variant("pepper_premium4", [
    (r"PEPPER_TAKE_PREMIUM = \d+.*", "PEPPER_TAKE_PREMIUM = 4         # was 8 — pay less premium"),
])
make_variant("pepper_bidsize50", [
    (r"PEPPER_BASE_BID_SIZE = \d+.*", "PEPPER_BASE_BID_SIZE = 50       # was 30 — fill faster"),
])

# ── Best guess combined ────────────────────────────────────────────────────
make_variant("combined_best", [
    (r"OSMIUM_DEFAULT_EDGE = \d+.*", "OSMIUM_DEFAULT_EDGE = 4        # was 5"),
    (r"OSMIUM_BASE_SIZE = \d+.*",    "OSMIUM_BASE_SIZE = 25          # was 20"),
    (r"PEPPER_TAKE_PREMIUM = \d+.*", "PEPPER_TAKE_PREMIUM = 4         # was 8"),
    (r"PEPPER_BASE_BID_SIZE = \d+.*","PEPPER_BASE_BID_SIZE = 50       # was 30"),
])

print("Done.")
