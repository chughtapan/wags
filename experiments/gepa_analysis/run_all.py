import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all GEPA analysis steps.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="1-14-prefinal",
        help="Run directory name or path under outputs/gepa_on_bfcl.",
    )
    return parser.parse_args()


def run_step(script: str, output_dir: str) -> None:
    result = subprocess.run(
        [sys.executable, script, "--output-dir", output_dir],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    args = parse_args()
    run_step("experiments/gepa_analysis/candidate_snapshots.py", args.output_dir)
    run_step("experiments/gepa_analysis/prompt_diff.py", args.output_dir)
    run_step("experiments/gepa_analysis/prompt_timeline.py", args.output_dir)


if __name__ == "__main__":
    main()
