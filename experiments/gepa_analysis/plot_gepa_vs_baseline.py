import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot GEPA vs baseline performance.")
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
            return arg_path if arg_path.is_absolute() else PROJECT_ROOT / arg_path
        if part == "outputs" and parts[idx + 1] == "gepa_on_bfcl":
            return PROJECT_ROOT / "outputs" / "gepa_analysis" / arg_path.name
    return PROJECT_ROOT / "outputs" / "gepa_analysis" / output_dir_arg

def main():
    args = parse_args()
    output_dir = resolve_analysis_dir(args.output_dir)
    df = pd.read_csv(output_dir / "candidate_snaps.csv")

    baseline_hash = df.loc[df["n_evals"].idxmax(), "instruction_hash"]
    baseline = df[df["instruction_hash"] == baseline_hash]
    if baseline.empty:
        raise ValueError("Baseline prompt not found")

    baseline_score = baseline["overall_pass_rate"].iloc[0]

    gepa = df[df["instruction_hash"] != baseline_hash]
    gepa = gepa[gepa["n_evals"] >= 10]

    # Calculate statistics
    improvements = gepa["overall_pass_rate"] - baseline_score
    n_improved = (improvements > 0).sum()
    n_total = len(improvements)
    avg_improvement = improvements.mean()

    fig, ax = plt.subplots(figsize=(8, 7))

    # Draw connecting lines with color based on improvement
    for _, row in gepa.iterrows():
        delta = row["overall_pass_rate"] - baseline_score
        color = '#2ecc71' if delta > 0 else '#e74c3c'
        alpha = min(0.6, 0.2 + abs(delta) * 2)  # More visible for larger changes
        ax.plot(
            [0, 1],
            [baseline_score, row["overall_pass_rate"]],
            color=color,
            alpha=alpha,
            linewidth=1.5
        )

    # Baseline point
    ax.scatter(
        [0],
        [baseline_score],
        color="black",
        s=200,
        label=f"Baseline ({baseline_score:.1%})",
        zorder=3,
        edgecolors='white',
        linewidths=2
    )

    # GEPA points with colors
    colors = ['#2ecc71' if x > baseline_score else '#e74c3c' 
              for x in gepa["overall_pass_rate"]]
    ax.scatter(
        [1] * len(gepa),
        gepa["overall_pass_rate"],
        c=colors,
        s=80,
        alpha=0.7,
        zorder=3,
        edgecolors='white',
        linewidths=1
    )

    # Add horizontal reference line at baseline
    ax.axhline(y=baseline_score, color='gray', linestyle='--', 
               alpha=0.3, linewidth=1, zorder=1)

    # Styling
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Baseline prompt", "GEPA prompts\n(n_evals > 10)"], fontsize=11)
    ax.set_ylabel("Overall pass rate on BFCL", fontsize=11)
    ax.set_ylim(max(0, gepa["overall_pass_rate"].min() - 0.05), 
                min(1, gepa["overall_pass_rate"].max() + 0.05))
    
    # Format y-axis as percentages
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0%}'))
    
    ax.set_title("Does GEPA Improve Prompt Performance?", 
                 fontsize=13, fontweight='bold', pad=15)
    
    # Add statistics text box
    stats_text = (f"Improved: {n_improved}/{n_total} ({n_improved/n_total:.1%})\n"
                  f"Avg change: {avg_improvement:+.1%}")
    ax.text(0.98, 0.02, stats_text,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='bottom',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    # Custom legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='black',
               markersize=10, label=f'Baseline ({baseline_score:.1%})', 
               markeredgecolor='white', markeredgewidth=2),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71',
               markersize=8, label='Improved', alpha=0.7),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c',
               markersize=8, label='Degraded', alpha=0.7)
    ]
    ax.legend(handles=legend_elements, loc='upper left', framealpha=0.9)

    ax.grid(axis='y', alpha=0.3, linestyle=':', linewidth=0.5)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_dir / "plot_gepa_vs_baseline.png", dpi=150)
    plt.close()

if __name__ == "__main__":
    main()
