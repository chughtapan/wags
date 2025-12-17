# NOTE:
# This script performs instruction-only optimization using GEPA over BFCL tests.
# The BFCL agent is invoked via pytest.

"""Simple GEPA-based instruction optimization for BFCL tests.

Usage:
    python experiments/optimize_gepa.py --test-subset multi_turn_base --num-tests <N>
"""

import argparse
import json
import subprocess
import hashlib
from pathlib import Path
from typing import Any, Optional

import dspy
from dspy.evaluate import Evaluate
from dspy.teleprompt import GEPA

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.benchmarks.bfcl import loader as bfcl_loader
from tests.utils.fastagent_helpers import MessageSerializer


# -------------------------
# Utilities
# -------------------------

def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stringify_question(question: Any) -> str:
    if isinstance(question, list) and question:
        first = question[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("content", ""))
    if isinstance(question, dict):
        return str(question.get("content", ""))
    if isinstance(question, str):
        return question
    return ""


# -------------------------
# DSPy wrappers
# -------------------------

class BFCLExample(dspy.Example):
    def __init__(
        self,
        test_id: str | None = None,
        question: str | None = None,
        expected_tools: list[str] | None = None,
        *,
        base: dspy.Example | None = None,
        **kwargs: Any,
    ):
        if base is not None:
            super().__init__(base=base, **kwargs)
        else:
            super().__init__(test_id=test_id, question=question, expected_tools=expected_tools or [], **kwargs)


class MetricFeedback(dspy.Prediction):
    def __init__(self, score: float, feedback: str) -> None:
        super().__init__(score=score, feedback=feedback)


class BFCLAgent(dspy.Module):
    def __init__(
        self,
        instruction_text: str,
        model: str,
        base_dir: Path,
        pytest_binary: str,
        enable_scoring_mode: bool,
    ) -> None:
        super().__init__()
        self.model = model
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.pytest_binary = pytest_binary
        self.enable_scoring_mode = enable_scoring_mode
        self._instruction_path = self.base_dir / "current_instruction.txt"

        instruction_signature = dspy.Signature("prompt_input -> prompt_output", instructions=instruction_text)
        self.prompt_predictor = dspy.Predict(instruction_signature)

    def forward(self, test_id: str, question: str) -> dspy.Prediction:
        instruction_text = self.get_instruction_text()
        self._instruction_path.write_text(instruction_text, encoding="utf-8")

        output_dir = self.base_dir / "runs" / test_id
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.pytest_binary,
            f"tests/benchmarks/bfcl/test_bfcl.py::test_bfcl[{test_id}]",
            "--model",
            self.model,
            "--instruction-file",
            str(self._instruction_path),
            "--output-dir",
            str(output_dir),
            "-q",
            "-x",
        ]

        if self.enable_scoring_mode:
            cmd.append("--gepa-scoring-mode")

        result = subprocess.run(cmd, capture_output=True, text=True)
        passed = result.returncode == 0
        tools_used = self._collect_tool_names(output_dir, test_id)

        return dspy.Prediction(
            test_id=test_id,
            passed=passed,
            tools_used=tools_used,
            output=result.stdout + result.stderr,
        )

    def get_instruction_text(self) -> str:
        instructions = getattr(self.prompt_predictor.signature, "instructions", "")
        if isinstance(instructions, (list, tuple)):
            return "\n".join(str(p) for p in instructions if p)
        return str(instructions or "")

    @staticmethod
    def _collect_tool_names(output_dir: Path, test_id: str) -> list[str]:
        complete_file = output_dir / "raw" / f"{test_id}_complete.json"
        if not complete_file.exists():
            return []
        try:
            data = json.loads(complete_file.read_text())
        except json.JSONDecodeError:
            return []
        calls = MessageSerializer.extract_tool_calls_by_turn(data)
        return [call.get("function") for turn in calls for call in turn if call.get("function")]


# -------------------------
# Metric
# -------------------------

def bfcl_metric_with_feedback(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Optional[Any] = None,
    pred_name: Optional[str] = None,
    pred_trace: Optional[Any] = None,
) -> MetricFeedback:
    score = 1.0 if pred.passed else 0.0
    feedback = [f"Test {gold.test_id} {'PASSED' if pred.passed else 'FAILED'}"]

    if not pred.passed:
        expected = set(gold.expected_tools)
        used = set(pred.tools_used)
        if expected and not used:
            feedback.append(f"No tools called; expected: {', '.join(expected)}")
        else:
            missing = expected - used
            extra = used - expected
            if missing:
                feedback.append(f"Missing tools: {', '.join(missing)}")
            if extra:
                feedback.append(f"Unexpected tools: {', '.join(extra)}")

    return MetricFeedback(score=score, feedback=" | ".join(feedback))


# -------------------------
# Data loading
# -------------------------

def load_test_cases(subset: str, limit: int) -> list[BFCLExample]:
    test_ids = bfcl_loader.find_tests_in_category(subset, limit=limit)
    examples: list[BFCLExample] = []
    for test_id in test_ids[:limit]:
        entry = bfcl_loader.load_test_entry(test_id)
        question = _stringify_question(entry.get("question", ""))
        expected_tools = entry.get("involved_classes", []) or []
        ex = BFCLExample(test_id=test_id, question=question, expected_tools=expected_tools)
        examples.append(ex.with_inputs("test_id", "question"))
    return examples


# -------------------------
# Main
# -------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-subset", default="multi_turn_base")
    parser.add_argument("--num-tests", type=int, default=10)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--reflection-model", default="gpt-5")
    parser.add_argument("--max-evaluations", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/gepa"))
    parser.add_argument("--auto", choices=["light", "medium", "heavy"], default=None)
    parser.add_argument("--instruction-file", type=Path, required=True)
    parser.add_argument("--pytest-binary", default="pytest")
    parser.add_argument("--gepa-scoring-mode", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    examples = load_test_cases(args.test_subset, args.num_tests)
    train_size = int(0.7 * len(examples))
    trainset, devset = examples[:train_size], examples[train_size:]

    instruction_text = args.instruction_file.read_text()
    instruction_hash = sha256_text(instruction_text)

    agent = BFCLAgent(
        instruction_text=instruction_text,
        model=args.model,
        base_dir=args.output_dir,
        pytest_binary=args.pytest_binary,
        enable_scoring_mode=args.gepa_scoring_mode,
    )

    # Baseline
    passed = sum(agent(test_id=e.test_id, question=e.question).passed for e in examples)
    baseline_score = passed / len(examples)
    (args.output_dir / "baseline.json").write_text(json.dumps({
        "instruction_hash": instruction_hash,
        "pass_rate": baseline_score,
        "passed": passed,
        "total": len(examples),
        "test_ids": [e.test_id for e in examples],
        "model": args.model,
    }, indent=2))

    # GEPA
    reflection_lm = dspy.LM(args.reflection_model)
    dspy.configure(lm=reflection_lm)

    gepa_kwargs = dict(
        metric=bfcl_metric_with_feedback,
        reflection_lm=reflection_lm,
        track_stats=True,
        log_dir=str(args.output_dir / "gepa_logs"),
        seed=42,
    )
    
    if args.auto is not None:
        gepa_kwargs["auto"] = args.auto
    else:
        gepa_kwargs["max_full_evals"] = args.max_evaluations
        
    gepa = GEPA(**gepa_kwargs)
    optimized_agent = gepa.compile(agent, trainset=trainset, valset=devset)
    results = optimized_agent.detailed_results

    # Dump candidates
    candidates = []
    for i, cand in enumerate(results.candidates):
        instr = cand.get_instruction_text()
        candidates.append({
            "candidate_id": i,
            "instruction_hash": sha256_text(instr),
            "instruction_text": instr,
            "val_score": results.val_aggregate_scores[i],
            "discovered_at_metric_call": results.discovery_eval_counts[i],
            "parents": results.parents[i],
        })
    (args.output_dir / "gepa_candidates.json").write_text(json.dumps(candidates, indent=2))

    # Pareto (simple: max score per val instance)
    best_ids = set().union(*results.per_val_instance_best_candidates)
    with open(args.output_dir / "gepa_pareto.txt", "w", encoding="utf-8") as f:
        f.write("GEPA Pareto Frontier\n====================\n\n")
        for i in sorted(best_ids, key=lambda i: results.val_aggregate_scores[i], reverse=True):
            f.write(f"Candidate {i} | score={results.val_aggregate_scores[i]:.3f}\n")
            f.write("-" * 40 + "\n")
            f.write(results.candidates[i].get_instruction_text() + "\n\n")

    # Final instruction
    final_instr = optimized_agent.get_instruction_text()
    (args.output_dir / "optimized_instructions.txt").write_text(final_instr)

    # Metadata
    meta = {
        "baseline_score": baseline_score,
        "final_score": max(results.val_aggregate_scores),
        "total_metric_calls": results.total_metric_calls,
        "num_full_val_evals": results.num_full_val_evals,
        "seed": results.seed,
    }
    (args.output_dir / "optimization_metadata.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
