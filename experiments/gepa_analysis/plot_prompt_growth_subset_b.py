import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ----------------------------
# CONFIG
# ----------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
CSV_PATH = REPO_ROOT / "outputs/gepa_on_bfcl/subset-b-final/analysis/candidates_table.csv"
EXPERT_CHARS = 1138
OUT_PATH = REPO_ROOT / "subset_b_prompt_growth.png"

# ----------------------------
# Load data
# ----------------------------

df = pd.read_csv(CSV_PATH)

# We want ONE point per instruction, ordered by first appearance
df = df.sort_values("snapshot_idx")

# ----------------------------
# Plot
# ----------------------------

plt.figure(figsize=(9, 5))

# GEPA prompt growth curve
plt.plot(
    df["snapshot_idx"],
    df["prompt_length_chars"],
    marker="o",
    linewidth=2,
    alpha=0.8,
    label="GEPA prompt length"
)

# Expert prompt: horizontal reference line
plt.axhline(
    y=EXPERT_CHARS,
    linestyle="--",
    linewidth=2,
    label="Expert prompt length"
)

# Expert marker (X), placed slightly after GEPA ends
x_expert = df["snapshot_idx"].max() + 5
plt.scatter(
    [x_expert],
    [EXPERT_CHARS],
    marker="x",
    s=120,
    linewidths=3
)

# ----------------------------
# Styling
# ----------------------------

plt.xlabel("GEPA Iteration (Candidate Index)")
plt.ylabel("Prompt Length (Characters)")
plt.title("Prompt Growth Over Time - Subset B")

plt.grid(True, linestyle="--", alpha=0.4)
plt.legend()
plt.tight_layout()

plt.savefig(OUT_PATH, dpi=200)
plt.show()

print(f"Saved plot to {'experiments/gepa_analysis' / OUT_PATH}")
