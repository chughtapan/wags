import matplotlib.pyplot as plt
from pathlib import Path
import pandas as pd
import numpy as np

def plot_prompt_search_timeline(candidate_df: pd.DataFrame, output_dir: Path):
    # Add discovery order
    df = candidate_df.copy()
    df["discovery_index"] = range(len(df))
    
    # Baseline = most evaluated prompt (more robust than "first seen")
    baseline_idx = df["n_evals"].idxmax()
    baseline = df.loc[baseline_idx]
    others = df.drop(index=baseline_idx)
    
    # Y values: dev pass rate; if NaN, place slightly below 0 to show "no dev eval"
    y = df["dev_pass_rate"].copy()
    no_dev_mask = y.isna()
    y_plot = y.copy()
    y_plot[no_dev_mask] = -0.05  # sentinel row for "no dev eval"
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Get colormap normalization based on all instruction lengths
    norm = plt.Normalize(
        vmin=df["instruction_length_lines"].min(),
        vmax=df["instruction_length_lines"].max()
    )
    cmap = plt.cm.viridis
    
    # Plot all non-baseline prompts
    scatter = ax.scatter(
        df.loc[df.index != baseline_idx, "discovery_index"],
        y_plot.loc[df.index != baseline_idx],
        c=df.loc[df.index != baseline_idx, "instruction_length_lines"],
        cmap="viridis",
        norm=norm,
        s=80,
        alpha=0.9,
    )
    
    # Plot baseline prompt with viridis color
    ax.scatter(
        baseline["discovery_index"],
        (-0.05 if pd.isna(baseline["dev_pass_rate"]) else baseline["dev_pass_rate"]),
        marker="*",
        s=250,
        c=[baseline["instruction_length_lines"]],
        cmap="viridis",
        norm=norm,
        # edgecolor="black",
        linewidth=2,
        label=f"Baseline (n={int(baseline['n_evals'])})",
        zorder=5,  # Ensure it's on top
    )
    
    # Add trend line for prompts with dev evals
    valid_mask = ~no_dev_mask
    if valid_mask.sum() > 1:
        z = np.polyfit(df.loc[valid_mask, "discovery_index"], 
                       df.loc[valid_mask, "dev_pass_rate"], 1)
        p = np.poly1d(z)
        ax.plot(df.loc[valid_mask, "discovery_index"], 
                p(df.loc[valid_mask, "discovery_index"]),
                "r--", alpha=0.3, linewidth=1.5, label="Trend")
    
    ax.set_title("GEPA Prompt Exploration (Dev Pass Rate)", 
                 fontsize=13, fontweight='bold')
    ax.set_xlabel("Prompt Discovery Order", fontsize=11)
    ax.set_ylabel("Dev Pass Rate", fontsize=11)
    
    # Make the "no dev eval" row interpretable
    ax.set_ylim(-0.08, 1.05)
    ax.axhline(-0.05, linestyle="--", linewidth=1, color='gray', alpha=0.5)
    ax.text(
        0, -0.048, "no dev eval",
        fontsize=9, va="bottom", style='italic', color='gray'
    )
    
    # Add grid for easier reading
    ax.grid(True, alpha=0.2, linestyle=':')
    
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Instruction Length (lines)", fontsize=10)
    
    ax.legend(loc="upper right", framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(output_dir / "prompt_search_timeline.png", dpi=150)
    plt.close()

output_dir = Path("./outputs/gepa_analysis/1-14-prefinal")
candidate_df = pd.read_csv(output_dir / "candidate_snaps.csv")
plot_prompt_search_timeline(candidate_df, output_dir)