import pandas as pd
from pathlib import Path
import difflib


def unified_prompt_diff(base_text: str, new_text: str) -> str:
    base_lines = base_text.splitlines()
    new_lines = new_text.splitlines()

    diff = difflib.unified_diff(
        base_lines,
        new_lines,
        fromfile="baseline",
        tofile="candidate",
        lineterm=""
    )

    return "\n".join(diff)

def main():
    output_dir = Path("./outputs/gepa_analysis/1-14-prefinal")
    df = pd.read_csv(output_dir / "candidate_snaps.csv")

    output_md = Path(output_dir / "prompt_diffs.md")

    # Baseline = most evaluated prompt
    baseline = df.loc[df["n_evals"].idxmax()]

    # Best non-baseline by overall pass rate
    best_non_baseline = (
        df.drop(index=baseline.name)
        .sort_values("overall_pass_rate", ascending=False)
        .iloc[0]
    )

    # Longest prompt (verbosity exploration)
    longest_prompt = (
        df.drop(index=baseline.name)
        .sort_values("instruction_length_lines", ascending=False)
        .iloc[0]
    )

    print("Baseline hash:", baseline["instruction_hash"])
    print("Best non-baseline hash:", best_non_baseline["instruction_hash"])
    print("Longest prompt hash:", longest_prompt["instruction_hash"])

    with output_md.open("w") as f:
        f.write("# Prompt Difference Analysis\n\n")

        def write_section(title, base, other):
            f.write(f"## {title}\n\n")
            f.write(f"**Baseline hash:** `{base['instruction_hash']}`\n\n")
            f.write(f"**Candidate hash:** `{other['instruction_hash']}`\n\n")
            f.write(
                f"- Overall pass rate: {other['overall_pass_rate']:.3f}\n"
                f"- Instruction length (lines): {other['instruction_length_lines']}\n\n"
            )

            diff_text = unified_prompt_diff(
                base["instruction_text"],
                other["instruction_text"],
            )

            f.write("```diff\n")
            f.write(diff_text if diff_text else "(No textual differences)\n")
            f.write("\n```\n\n")

        write_section(
            "Baseline vs Best Non-Baseline Prompt",
            baseline,
            best_non_baseline,
        )

        write_section(
            "Baseline vs Longest Prompt",
            baseline,
            longest_prompt,
        )

if __name__ == "__main__":
    main()