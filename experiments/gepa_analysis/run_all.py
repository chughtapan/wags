import argparse
import subprocess
import sys
import os
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all GEPA analysis steps.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="1-14-prefinal",
        help="Run directory name or path under outputs/gepa_on_bfcl.",
    )
    return parser.parse_args()


def run_step(script: str, output_dir: str, cwd: str = PROJECT_ROOT) -> None:
    result = subprocess.run(
        [sys.executable, script, "--output-dir", output_dir],
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    args = parse_args()
    # Run candidate_snapshots first
    run_step(os.path.join(CURRENT_DIR, "candidate_snapshots.py"), args.output_dir, cwd=PROJECT_ROOT)

    # Verify that candidate_snapshots produced the raw dataframe before continuing.
    run_name = Path(args.output_dir).name
    raw_csv = Path("outputs/gepa_analysis") / run_name / "candidate_evals_raw.csv"
    if not raw_csv.exists():
        raise SystemExit(f"candidate_snapshots did not produce expected file: {raw_csv}")

    # Run remaining analysis scripts from the analysis output directory so they can read/write
    # candidate_evals_raw.csv and other local files.
    analysis_cwd = str((Path(PROJECT_ROOT) / "outputs" / "gepa_analysis" / run_name).resolve())

    run_step(os.path.join(CURRENT_DIR, "md_prompt_diff.py"), args.output_dir)
    run_step(os.path.join(CURRENT_DIR, "plot_gepa_vs_baseline.py"), args.output_dir, cwd=analysis_cwd)
    run_step(os.path.join(CURRENT_DIR, "plot_prompt_ci_comparison.py"), args.output_dir, cwd=analysis_cwd)
    run_step(os.path.join(CURRENT_DIR, "plot_generalization_gap.py"), args.output_dir, cwd=analysis_cwd)

if __name__ == "__main__":
    main()
