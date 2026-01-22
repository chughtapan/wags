import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot generalization (Train vs Dev) or Efficiency.")
    parser.add_argument("--output-dir", type=str, default="1-14-prefinal")
    return parser.parse_args()

def resolve_analysis_dir(output_dir_arg: str) -> Path:
    arg_path = Path(output_dir_arg)
    parts = arg_path.parts
    for idx, part in enumerate(parts[:-1]):
        if part == "outputs" and parts[idx + 1] == "gepa_analysis":
            return arg_path if arg_path.is_absolute() else PROJECT_ROOT / arg_path
        if part == "outputs" and parts[idx + 1] == "gepa_on_bfcl":
            return PROJECT_ROOT / "outputs" / "gepa_analysis" / arg_path.name
    return PROJECT_ROOT / "outputs" / "gepa_analysis" / output_dir_arg

def main():
    args = parse_args()
    output_dir = resolve_analysis_dir(args.output_dir)
    
    # Load Data
    csv_path = output_dir / "candidate_snaps.csv"
    if not csv_path.exists():
        print(f"Error: {csv_path} not found.")
        return
        
    df = pd.read_csv(csv_path)
    
    # Identify Baseline
    # Assuming baseline is the one with the most evals if not explicitly marked, 
    # or usually the first one. Let's look for the highest N_evals as a heuristic 
    # or the one with specific hash if known. 
    # For this script, we'll assume the one with max n_evals is baseline/reference.
    # Baseline is the first row
    baseline_row = df.iloc[0]
    baseline_hash = baseline_row["instruction_hash"]
    
    # Filter for valid GEPA prompts (min 5 evals to reduce noise)
    gepa = df[df["instruction_hash"] != baseline_hash]
    gepa = gepa[gepa["n_evals"] >= 5]

    # --- DECISION LOGIC: TRAIN/DEV vs LENGTH/SCORE ---
    # Check if we have valid split data
    has_splits = (
        "train_pass_rate" in df.columns and 
        "dev_pass_rate" in df.columns and 
        df["train_pass_rate"].notna().sum() > 0 and 
        df["dev_pass_rate"].notna().sum() > 0
    )

    # Prefer generalization if splits exist and GEPA has valid dev rates; otherwise fallback to efficiency
    if has_splits and gepa["dev_pass_rate"].notna().sum() > 0:
        plot_generalization(df, gepa, baseline_row, output_dir)
    else:
        plot_efficiency(df, gepa, baseline_row, output_dir)
        

def plot_generalization(df, gepa, baseline, output_dir):
    """Plots Train vs Dev performance to identify overfitting."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 1. The Diagonal (Identity Line)
    lims = [
        min(df["train_pass_rate"].min(), df["dev_pass_rate"].min()) * 0.9,
        max(df["train_pass_rate"].max(), df["dev_pass_rate"].max()) * 1.05
    ]
    ax.plot(lims, lims, color='gray', linestyle='--', alpha=0.3, zorder=1, label="Perfect Generalization (y=x)")
    
    # Shaded Region for Overfitting (Below diagonal)
    ax.fill_between(lims, [0, 0], lims, color='red', alpha=0.03, label="Overfitting Zone")

    # 2. Scatter Points
    # Color by improvement over baseline dev score
    base_dev = baseline["dev_pass_rate"]
    
    # Define colors
    colors = []
    for val in gepa["dev_pass_rate"]:
        if val > base_dev: colors.append("#2ecc71") # Green
        elif val < base_dev * 0.95: colors.append("#e74c3c") # Red
        else: colors.append("#95a5a6") # Grey

    scatter = ax.scatter(
        gepa["train_pass_rate"], 
        gepa["dev_pass_rate"], 
        c=colors, 
        s=80, 
        alpha=0.7, 
        edgecolors='white', 
        linewidth=1,
        zorder=3
    )

    # 3. Baseline Marker
    ax.scatter(
        baseline["train_pass_rate"], 
        baseline["dev_pass_rate"], 
        c='#2c3e50', 
        s=250, 
        marker='*', 
        zorder=4, 
        edgecolors='white', 
        linewidth=1.5,
        label=f"Baseline ({baseline['dev_pass_rate']:.1%})"
    )

    # 4. Labels and Titles
    ax.set_xlabel("Train Split Pass Rate", fontsize=11, fontweight='bold')
    ax.set_ylabel("Dev Split Pass Rate", fontsize=11, fontweight='bold')
    ax.set_title("Generalization Gap: Are Prompts Overfitting?", fontsize=14, pad=15)
    
    # Format axes
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    
    # 5. Annotation for Best Prompt
    # Guard against all-NA dev_pass_rate (idxmax can return nan -> KeyError)
    if gepa["dev_pass_rate"].notna().any():
        best_gepa = gepa.loc[gepa["dev_pass_rate"].idxmax()]
        
        ax.annotate(
            f"Best GEPA\n({best_gepa['dev_pass_rate']:.1%})",
            xy=(best_gepa["train_pass_rate"], best_gepa["dev_pass_rate"]),
            xytext=(10, 10), textcoords='offset points',
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2"),
            fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc="wheat", alpha=0.8)
        )
    else:
        print("No valid GEPA dev_pass_rate values; skipping generalization-gap plotting.")
        return

    improved_count = (gepa["dev_pass_rate"] > base_dev).sum()
    neutral_count = ((gepa["dev_pass_rate"] <= base_dev) & (gepa["dev_pass_rate"] >= base_dev * 0.95)).sum()
    declined_count = (gepa["dev_pass_rate"] < base_dev * 0.95).sum()

    legend_elements = [
        Line2D([0], [0], marker='*', color='w', markerfacecolor='#2c3e50',
               markersize=12, label=f"Baseline ({baseline['dev_pass_rate']:.1%})",
               markeredgecolor='white', markeredgewidth=1.5),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71',
               markersize=8, label=f"Above baseline (n={improved_count})",
               markeredgecolor='white', markeredgewidth=1),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6',
               markersize=8, label=f"Within 5% of baseline (n={neutral_count})",
               markeredgecolor='white', markeredgewidth=1),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c',
               markersize=8, label=f"Below baseline (n={declined_count})",
               markeredgecolor='white', markeredgewidth=1),
        Line2D([0], [0], color='gray', linestyle='--', linewidth=1.5,
               label="Perfect generalization (y=x)"),
        Patch(facecolor='red', alpha=0.08, label="Overfitting zone (dev < train)"),
    ]
    ax.legend(handles=legend_elements, loc='lower right', framealpha=0.95)
    ax.grid(True, alpha=0.2, linestyle='--')
    
    # Remove top/right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_dir / "plot_generalization_gap.png", dpi=200)
    print(f"Saved generalization plot to {output_dir / 'plot_generalization_gap.png'}")
    plt.close()

def plot_efficiency(df, gepa, baseline, output_dir):
    """Fallback: Plots Length vs Performance."""
    fig, ax = plt.subplots(figsize=(10, 7))
    
    base_score = baseline["overall_pass_rate"]
    
    # Colors
    colors = ['#2ecc71' if x > base_score else '#e74c3c' for x in gepa["overall_pass_rate"]]
    
    ax.scatter(
        gepa["instruction_length_lines"], 
        gepa["overall_pass_rate"], 
        c=colors, 
        s=80, 
        alpha=0.7, 
        edgecolors='white',
        zorder=3
    )
    
    ax.scatter(
        baseline["instruction_length_lines"], 
        base_score, 
        c='#2c3e50', 
        s=250, 
        marker='*', 
        zorder=4, 
        label=f"Baseline ({base_score:.1%})",
        edgecolors='white'
    )
    
    ax.axhline(base_score, color='gray', linestyle='--', alpha=0.3, zorder=1)
    
    ax.set_xlabel("Instruction Length (Lines)", fontsize=11)
    ax.set_ylabel("Overall Pass Rate", fontsize=11)
    ax.set_title("Prompt Efficiency: Performance vs. Verbosity", fontsize=14, pad=15)
    
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    improved_count = (gepa["overall_pass_rate"] > base_score).sum()
    declined_count = (gepa["overall_pass_rate"] <= base_score).sum()
    legend_elements = [
        Line2D([0], [0], marker='*', color='w', markerfacecolor='#2c3e50',
               markersize=12, label=f"Baseline ({base_score:.1%})",
               markeredgecolor='white', markeredgewidth=1.5),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71',
               markersize=8, label=f"Above baseline (n={improved_count})",
               markeredgecolor='white', markeredgewidth=1),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c',
               markersize=8, label=f"Below baseline (n={declined_count})",
               markeredgecolor='white', markeredgewidth=1),
        Line2D([0], [0], color='gray', linestyle='--', linewidth=1.5,
               label="Baseline pass rate"),
    ]
    ax.legend(handles=legend_elements, framealpha=0.95)
    ax.grid(True, alpha=0.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_dir / "plot_efficiency_frontier.png", dpi=200)
    print(f"Saved efficiency plot to {output_dir / 'plot_efficiency_frontier.png'}")
    plt.close()

if __name__ == "__main__":
    main()
