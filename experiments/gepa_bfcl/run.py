"""
run.py

Orchestrator for running GEPA-based instruction optimization 
experiments on BFCL tests with logging/artifacts

Run once per experiment with 
`python -m experiments.gepa_bfcl.run --instruction-file path/to/instruction.txt [other options]`
"""

from __future__ import annotations
import argparse
import json
import os
import platform
import sys
import time
import uuid
from pathlib import Path
from typing import Any
import shlex
import random

import dspy
from dspy.teleprompt import GEPA

from .agent import BFCLAgent
from .data_utils import load_test_cases, extract_test_number, parse_test_number_spec
from .metrics import bfcl_metric_with_feedback, build_score_definition
from .env_utils import validate_model_environment
from .logging_utils import (
    RUN_CTX,
    RunContext,
    TeeIO,
    append_jsonl,
    safe_json,
    sha256_text,
    try_git_info,
    utc_now_iso,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GEPA instruction optimization on BFCL"
    )

    parser.add_argument("--test-subset", default="multi_turn_base")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-tests", type=int, default=None)
    parser.add_argument("--test-numbers", type=str, default=None)
    
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--reflection-model", default="gpt-5")

    parser.add_argument("--max-evaluations", type=int, default=20)
    parser.add_argument("--auto", choices=["light", "medium", "heavy"], default=None)

    parser.add_argument(
        "--instruction-file",
        type=Path,
        required=True,
        help="Path to initial instruction prompt.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/gepa_on_bfcl"),
    )

    parser.add_argument("--pytest-binary", default="pytest")
    parser.add_argument("--gepa-scoring-mode", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    validate_model_environment([args.model, args.reflection_model])
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Console mirroring
    console_log_path = args.output_dir / "console.log"
    console_log_f = console_log_path.open("w", encoding="utf-8")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = TeeIO(real_out, console_log_f)
    sys.stderr = TeeIO(real_err, console_log_f)
    
    # Metadata initialization
    overall_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # ---- Persist exact rerun command ----
    python_executable = sys.executable
    script_path = Path(__file__).resolve()

    argv = [python_executable, str(script_path)] + sys.argv[1:]
    command_str = shlex.join(argv)

    command_path = args.output_dir / "command.sh"
    command_path.write_text(
        "#!/usr/bin/env bash\n\n" + command_str + "\n",
        encoding="utf-8",
    )

    # Make it executable for convenience
    command_path.chmod(0o755)

    
    metric_calls_path = args.output_dir / "metric_calls.jsonl"
    candidate_snapshots_path = args.output_dir / "candidate_snapshots.jsonl"
    reflection_calls_path = args.output_dir / "reflection_calls.jsonl"
    run_index_path = args.output_dir / "run_index.jsonl"
    
    score_definition = build_score_definition()

    try:
        print(f"[{utc_now_iso()}] RUN_ID={run_id}")
        print(f"[{utc_now_iso()}] output_dir={args.output_dir}")
        
        selected_test_numbers: set[int] | None = None
        if args.test_numbers:
            selected_test_numbers = parse_test_number_spec(args.test_numbers)

        # Load dataset
        t_load = time.perf_counter()
        all_examples = load_test_cases(args.test_subset, limit=None)

        examples = list(all_examples)

        # Explicit numeric test selection
        if selected_test_numbers is not None:
            before = len(examples)

            matched = []
            matched_numbers = set()

            for e in examples:
                num = extract_test_number(e.test_id)
                if num in selected_test_numbers:
                    matched.append(e)
                    matched_numbers.add(num)

            examples = matched
            after = len(examples)

            print(
                f"[{utc_now_iso()}] Selected tests by number: "
                f"{sorted(matched_numbers)} ({after}/{len(selected_test_numbers)} found"
            )

        # Shuffle & slice
        rng = random.Random(args.seed)

        if args.shuffle:
            rng.shuffle(examples)

        if args.num_tests is not None:
            if selected_test_numbers is not None:
                print(
                    f"[{utc_now_iso()}] --test-numbers provided; ignoring --num-tests"
                )
            else:
                examples = examples[: args.num_tests]


                
        train_size = int(0.7 * len(examples))
        trainset = examples[:train_size]
        devset = examples[train_size:]
        timings["load_dataset_s"] = time.perf_counter() - t_load
        
        # Split dataset
        train_ids = {e.test_id for e in trainset}
        dev_ids = {e.test_id for e in devset}

        (args.output_dir / "dataset_split.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "test_subset": args.test_subset,
                    "shuffle": args.shuffle,
                    "seed": args.seed,
                    "num_tests": args.num_tests,
                    "examples_used_ordered": [e.test_id for e in examples],
                    "train_ids": sorted(train_ids),
                    "dev_ids": sorted(dev_ids),
                    "test_number_selection": (
                        sorted(selected_test_numbers) if selected_test_numbers is not None else None
                    ),
                    "selection_mode": (
                        "explicit_numbers" if selected_test_numbers is not None
                        else "first_n" if args.num_tests is not None
                        else "all"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
                
        # Initialize global run context
        global RUN_CTX
        RUN_CTX = RunContext(
            run_id=run_id,
            output_dir=args.output_dir,
            metric_calls_path=metric_calls_path,
            candidate_snapshots_path=candidate_snapshots_path,
            run_index_path=run_index_path,
            train_ids=train_ids,
            dev_ids=dev_ids,
            score_definition=score_definition
        )
        
        # Load initial instructions
        instruction_text = args.instruction_file.read_text(encoding="utf-8")
        instruction_hash = sha256_text(instruction_text)
        
        # Write the run manifest
        manifest = {
            "run_id": run_id,
            "created_at": utc_now_iso(),
            "argv": sys.argv,
            "args": safe_json(vars(args)),
            "instruction_file": str(args.instruction_file),
            "instruction_hash": instruction_hash,
            "score_definition": score_definition,
            "test_selection": {
                "mode": (
                    "explicit_numbers" if selected_test_numbers is not None
                    else "first_n" if args.num_tests is not None
                    else "all"
                ),
                "test_numbers": (
                    sorted(selected_test_numbers) if selected_test_numbers is not None else None
                ),
                "num_tests": args.num_tests,
                "shuffle": args.shuffle,
                "seed": args.seed,
            },
            "models": {
                "agent_model": args.model,
                "reflection_model": args.reflection_model
            },
            "dataset_split": {
                "train_ids": sorted(train_ids),
                "dev_ids": sorted(dev_ids),
            },
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "cwd": os.getcwd(),
            },
            **try_git_info(),
        }
        (args.output_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        
        # Create LMs
        reflection_lm = dspy.LM(args.reflection_model)
        execution_lm = dspy.LM(args.model)

        # Always configure a global LM (reflection-only by policy)
        dspy.configure(lm=reflection_lm)

        
        # Create agent
        agent = BFCLAgent(
            instruction_text=instruction_text,
            model=args.model,
            execution_lm=execution_lm,
            base_dir=args.output_dir,
            pytest_binary=args.pytest_binary,
            enable_scoring_mode=args.gepa_scoring_mode,
        )
        
        # Run and evaluate baseline - no GEPA!
        t_base = time.perf_counter()
        baseline_valid = 0
        baseline_details: list[dict[str, Any]] = []

        for ex in examples:
            pred = agent(test_id=ex.test_id, question=ex.question)

            valid = False
            if pred.evaluation:
                valid = bool(
                    pred.evaluation.get("validation", {}).get("valid", False)
                )

            baseline_valid += int(valid)
            baseline_details.append(
                {
                    "test_id": ex.test_id,
                    "valid": valid,
                    "run_dir": pred.run_dir,
                    "eval_error": pred.eval_error,
                }
            )

        timings["baseline_s"] = time.perf_counter() - t_base
        
        # Persist baseline
        baseline_valid_rate = baseline_valid / max(len(examples), 1)

        (args.output_dir / "baseline.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "instruction_hash": instruction_hash,
                    "bfcl_valid_rate": baseline_valid_rate,
                    "valid": baseline_valid,
                    "total": len(examples),
                    "runs": baseline_details,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            f"[{utc_now_iso()}] Baseline BFCL valid rate: "
            f"{baseline_valid_rate:.3f} ({baseline_valid}/{len(examples)})"
        )
        
        # Finalize GEPA parameters
        t_gepa = time.perf_counter()
        gepa_kwargs: dict[str, Any] = {
            "metric": bfcl_metric_with_feedback,
            "reflection_lm": reflection_lm,
            "track_stats": True,
            "log_dir": str(args.output_dir / "gepa_logs"),
            "seed": 42,
        }

        if args.auto is not None:
            gepa_kwargs["auto"] = args.auto
        else:
            gepa_kwargs["max_full_evals"] = args.max_evaluations
            
        (args.output_dir / "gepa_config.json").write_text(
            json.dumps(safe_json(gepa_kwargs), indent=2),
            encoding="utf-8",
        )
        
        # Create and run GEPA optimizer
        gepa = GEPA(**gepa_kwargs)
        
        reflection_lm.history.clear()
        optimized_agent = gepa.compile(
            agent,
            trainset=trainset,
            valset=devset,
        )

        for i, entry in enumerate(reflection_lm.history):
            record = {
                "ts": entry.get("timestamp"),
                "run_id": run_id,
                "call_index": i,
                "model": entry.get("model") or args.reflection_model,
                "model_type": entry.get("model_type"),

                # Prompting
                "prompt": entry.get("prompt"),
                "messages": entry.get("messages"),

                # Outputs
                "raw_response": entry.get("response"),
                "outputs": entry.get("outputs"),

                # Generation config
                "kwargs": entry.get("kwargs"),

                # Usage & cost
                "usage": entry.get("usage"),
                "cost": entry.get("cost"),

                # Traceability
                "uuid": entry.get("uuid"),
            }

            append_jsonl(reflection_calls_path, safe_json(record))

        results = optimized_agent.detailed_results
        timings["gepa_compile_s"] = time.perf_counter() - t_gepa
        
        # Final candidates summary (still useful)
        candidates = []
        for i, cand in enumerate(results.candidates):
            instr = cand.get_instruction_text()
            candidates.append(
                {
                    "candidate_id": i,
                    "instruction_hash": sha256_text(instr),
                    "instruction_text": instr,
                    "val_score": results.val_aggregate_scores[i],
                    "discovered_at_metric_call": results.discovery_eval_counts[i],
                    "parents": results.parents[i],
                }
            )
        (args.output_dir / "gepa_candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")

        # Pareto
        best_ids = set().union(*results.per_val_instance_best_candidates)
        with open(args.output_dir / "gepa_pareto.txt", "w", encoding="utf-8") as f:
            f.write("GEPA Pareto Frontier\n====================\n\n")
            for i in sorted(best_ids, key=lambda i: results.val_aggregate_scores[i], reverse=True):
                f.write(f"Candidate {i} | score={results.val_aggregate_scores[i]:.3f}\n")
                f.write("-" * 40 + "\n")
                f.write(results.candidates[i].get_instruction_text() + "\n\n")

        final_instr = optimized_agent.get_instruction_text()
        (args.output_dir / "optimized_instructions.txt").write_text(final_instr, encoding="utf-8")

        # Scores file (explicit: which examples and how computed)
        scores_payload = {
            "run_id": run_id,
            "score_definition": score_definition,
            "dataset_split": {
                "train_ids": sorted(train_ids),
                "dev_ids": sorted(dev_ids),
            },
            "baseline": {
                "bfcl_valid_rate_over_all_examples": baseline_valid_rate,
                "examples_used": [e.test_id for e in examples],
                "valid_count": baseline_valid,
                "total_count": len(examples),
            },
            "gepa": {
                "objective": "binary hard_valid (1.0 pass / 0.0 fail) aggregated over dev set by GEPA",
                "val_aggregate_scores": safe_json(results.val_aggregate_scores),
                "candidate_count": len(results.candidates),
            },
            "note": "For per-evaluation, per-test, per-step details see metric_calls.jsonl (append-only).",
        }
        (args.output_dir / "scores.json").write_text(json.dumps(scores_payload, indent=2), encoding="utf-8")

        # Metadata + timings
        timings["total_wall_s"] = time.perf_counter() - overall_t0
        (args.output_dir / "timings.json").write_text(json.dumps({"run_id": run_id, **timings}, indent=2), encoding="utf-8")

        meta = {
            "run_id": run_id,
            "baseline_bfcl_valid_rate": baseline_valid_rate,
            "final_score": max(results.val_aggregate_scores) if results.val_aggregate_scores else None,
            "total_metric_calls": results.total_metric_calls,
            "num_full_val_evals": results.num_full_val_evals,
            "seed": results.seed,
        }
        (args.output_dir / "optimization_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        print(f"[{utc_now_iso()}] Done. See {args.output_dir}/run_manifest.json, scores.json, metric_calls.jsonl")


    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        sys.stdout = real_out
        sys.stderr = real_err
        console_log_f.close()

if __name__ == "__main__":
    main()