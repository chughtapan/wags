import numpy as np
from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import pandas as pd

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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot prompt search timeline.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="1-14-prefinal",
        help="Run directory name or path under outputs/gepa_on_bfcl (analysis lives in outputs/gepa_analysis).",
    )
    return parser.parse_args()

def resolve_analysis_dir(output_dir_arg: str) -> Path:
    arg_path = Path(output_dir_arg)
    parts = arg_path.parts
    for idx, part in enumerate(parts[:-1]):
        if part == "outputs" and parts[idx + 1] == "gepa_analysis":
            return arg_path
        if part == "outputs" and parts[idx + 1] == "gepa_on_bfcl":
            return Path("./outputs/gepa_analysis") / arg_path.name
    return Path("./outputs/gepa_analysis") / output_dir_arg


def main():
    args = parse_args()
    output_dir = resolve_analysis_dir(args.output_dir)
    candidate_df = pd.read_csv(output_dir / "candidate_snaps.csv")
    plot_prompt_search_timeline(candidate_df, output_dir)


if __name__ == "__main__":
    main()
