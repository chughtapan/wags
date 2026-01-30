from pathlib import Path
import argparse
import json

import pandas as pd


def load_candidate_snapshots(path: Path) -> pd.DataFrame:
    rows = []

    with path.open() as f:
        for line in f:
            record = json.loads(line)

            eval_info = record.get("latest_eval", {})

            rows.append({
                "ts": pd.to_datetime(record["ts"], utc=True),
                "instruction_hash": record["instruction_hash"],
                "instruction_text": record["instruction_text"],
                "test_id": eval_info.get("test_id"),
                "split": eval_info.get("split"),
                "hard_valid": eval_info.get("hard_valid"),
                "score": eval_info.get("final"),
            })

    return pd.DataFrame(rows)


def build_candidate_prompt_table(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("instruction_hash")

    rows = []

    for instruction_hash, g in grouped:
        instruction_text = g["instruction_text"].iloc[0]

        train_scores = g[g["split"] == "train"]["score"]
        dev_scores = g[g["split"] == "dev"]["score"]

        rows.append({
            "instruction_hash": instruction_hash,
            "instruction_text": instruction_text,
            "first_seen_ts": g["ts"].min(),
            "last_seen_ts": g["ts"].max(),
            "n_evals": len(g),
            "train_pass_rate": train_scores.mean() if not train_scores.empty else None,
            "dev_pass_rate": dev_scores.mean() if not dev_scores.empty else None,
            "overall_pass_rate": g["score"].mean(),
            "instruction_length_chars": len(instruction_text),
            "instruction_length_lines": instruction_text.count("\n") + 1,
        })

    candidate_df = pd.DataFrame(rows)

    return candidate_df.sort_values("first_seen_ts").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate prompt table.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="1-14-prefinal",
        help="Run directory name or path under outputs/gepa_on_bfcl (analysis lives in outputs/gepa_analysis).",
    )
    return parser.parse_args()

def resolve_run_dir(output_dir_arg: str) -> Path:
    arg_path = Path(output_dir_arg)
    parts = arg_path.parts
    for idx, part in enumerate(parts[:-1]):
        if part == "outputs" and parts[idx + 1] == "gepa_on_bfcl":
            return arg_path
        if part == "outputs" and parts[idx + 1] == "gepa_analysis":
            return Path("./outputs/gepa_on_bfcl") / arg_path.name
    return Path("./outputs/gepa_on_bfcl") / output_dir_arg


def main():
    args = parse_args()
    run_dir = resolve_run_dir(args.output_dir)
    run_name = run_dir.name
    output_dir = Path("./outputs/gepa_analysis") / run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    snapshots_path = Path(run_dir / "candidate_snapshots.jsonl")

    df_raw = load_candidate_snapshots(snapshots_path)
    candidate_df = build_candidate_prompt_table(df_raw)

    candidate_df.to_csv(output_dir / "candidate_snaps.csv", index=False)

    print("\n=== Candidate Prompt Summary ===")
    print(f"Total snapshot rows: {len(df_raw)}")
    print(f"Unique prompts: {len(candidate_df)}")

    print("\nTop prompts by dev pass rate:")
    print(
        candidate_df
        .sort_values("dev_pass_rate", ascending=False)
        .head(5)[
            [
                "instruction_hash",
                "n_evals",
                "dev_pass_rate",
                "instruction_length_lines",
            ]
        ]
    )


if __name__ == "__main__":
    main()
