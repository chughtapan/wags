import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import matplotlib.ticker as mtick

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
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
    csv_path = output_dir / "candidate_snaps.csv"
    
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    df = pd.read_csv(csv_path)

    # 1. Identify Baseline & Calculate Delta
    # Assuming baseline is the one with max evals (or specific hash logic)
    baseline_hash = df.loc[df["n_evals"].idxmax(), "instruction_hash"]
    baseline_score = df.loc[df["instruction_hash"] == baseline_hash, "overall_pass_rate"].iloc[0]

    df = df[df["instruction_hash"] != baseline_hash].copy()
    df["delta"] = df["overall_pass_rate"] - baseline_score
    
    # 2. Sort by performance
    df = df.sort_values("delta").reset_index(drop=True)

    # 3. Setup Plot
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Define simple colors
    # Green for positive, Red for negative
    colors = np.where(df["delta"] > 0, '#2ca02c', '#d62728')
    
    # Plot Dots
    y_pos = range(len(df))
    ax.scatter(
        df["delta"], 
        y_pos, 
        c=colors, 
        s=50, 
        alpha=0.8, 
        edgecolors='none'
    )

    # 4. Add Baseline Marker
    ax.axvline(0, color="black", linestyle="--", linewidth=1, alpha=0.3)
    ax.text(0, -1, "Baseline", ha='center', va='top', fontsize=9, color='gray')

    # 5. Highlight the Winner
    if not df.empty:
        best_row = df.iloc[-1]
        if best_row["delta"] > 0:
            ax.annotate(
                f"Best Prompt\n+{best_row['delta']:.1%}", 
                xy=(best_row["delta"], y_pos[-1]), 
                xytext=(-10, 0), 
                textcoords="offset points",
                ha='right', va='center',
                fontsize=10, fontweight='bold', color='#2ca02c',
                arrowprops=dict(arrowstyle="->", color='#2ca02c', connectionstyle="arc3,rad=-0.1")
            )

    # 6. Aesthetics & Cleaning
    # Remove Y axis completely (we care about distribution, not individual rank IDs)
    ax.set_yticks([])
    
    # Remove borders (spines) for a cleaner look
    ax.spines['left'].set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#dddddd')
    
    # Format X axis as percentage
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_xlabel("Change in Pass Rate", fontsize=10, color='#555555', labelpad=10)
    
    # Add a direct title
    n_better = sum(df["delta"] > 0)
    title_text = f"Performance Summary: {n_better} prompts beat the baseline"
    ax.set_title(title_text, fontsize=14, fontweight='bold', loc='left', pad=15)

    plt.tight_layout()
    plt.savefig(output_dir / "plot_prompt_comparison_simple.png", dpi=150)
    print(f"Saved to {output_dir / 'plot_prompt_comparison_simple.png'}")
    plt.close()

if __name__ == "__main__":
    main()