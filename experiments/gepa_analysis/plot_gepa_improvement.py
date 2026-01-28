import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# -------------------------------------------------
# CONFIG — EDIT THESE PATHS + NAMES
# -------------------------------------------------

SUBSETS = {
    "Subset A": Path(__file__).parent.parent.parent / "outputs/gepa_on_bfcl/subset-a-final/analysis/candidates_table.csv",
    "Subset B": Path(__file__).parent.parent.parent / "outputs/gepa_on_bfcl/subset-b-final/analysis/candidates_table.csv",
    "Subset C": Path(__file__).parent.parent.parent / "outputs/gepa_on_bfcl/subset-c-final/analysis/candidates_table.csv",
}

OUT_PATH = "experiments/gepa_analysis/gepa_improvement_over_time.png"

# -------------------------------------------------
# LOAD + PLOT
# -------------------------------------------------

plt.figure(figsize=(10, 6))

for subset_name, csv_path in SUBSETS.items():
    df = pd.read_csv(csv_path)

    # Keep only candidates that were evaluated on dev at least once
    df = df[df["dev_coverage"] > 0].copy()

    # Sort by iteration (snapshot index)
    df = df.sort_values("snapshot_idx")

    # Running best dev accuracy
    df["best_so_far"] = df["dev_pass_rate"].cummax()

    # Scatter: all candidates
    plt.scatter(
        df["snapshot_idx"],
        df["dev_pass_rate"],
        alpha=0.4,
        s=35,
        label=f"{subset_name} candidates"
    )

    # Line: improvement envelope
    plt.plot(
        df["snapshot_idx"],
        df["best_so_far"],
        linewidth=2,
        label=f"{subset_name} best-so-far"
    )

# -------------------------------------------------
# STYLING
# -------------------------------------------------

plt.xlabel("GEPA Iteration (Candidate Index)")
plt.ylabel("Dev Pass Rate")
plt.title("GEPA Instruction Optimization Progress Across BFCL Subsets")

plt.ylim(-0.02, 1.02)
plt.grid(True, linestyle="--", alpha=0.4)
plt.legend()
plt.tight_layout()

plt.savefig(OUT_PATH, dpi=200)
plt.show()

print(f"Saved plot to {OUT_PATH}")
