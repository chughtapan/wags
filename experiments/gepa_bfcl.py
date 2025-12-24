# NOTE:
# This script performs instruction-only optimization using GEPA over BFCL tests.
# The BFCL agent is invoked via pytest.

"""Simple GEPA-based instruction optimization for BFCL tests.

Usage:
    python experiments/gepa_bfcl.py --test-subset multi_turn_base --num-tests <N>
"""

import argparse
import json
import subprocess
import hashlib
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

import dspy
from dspy.evaluate import Evaluate
from dspy.teleprompt import GEPA

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.benchmarks.bfcl import loader as bfcl_loader
from tests.benchmarks.bfcl import evaluator as bfcl_evaluator
from tests.utils.fastagent_helpers import MessageSerializer


# -------------------------
# Utilities
# -------------------------


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stringify_question(question: Any) -> str:
    """Best-effort stringify for logging/trace only. BFCL is multi-turn; this just picks the first user content."""
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


def _fn_name(executable_call: str) -> str:
    """Extract function name from BFCL executable string like `grep(file='x')`."""
    if not executable_call:
        return ""
    idx = executable_call.find("(")
    return executable_call[:idx] if idx != -1 else executable_call


def _soft_turn_score(gt_turn: list[str], pred_turn: list[str]) -> float:
    """
    Soft, cheap signal to help GEPA search:
    - 1.0 if exact match (order+args string exactness)
    - else, score based on overlap of function names (ignores args) with order-insensitive F1-ish heuristic
    """
    if gt_turn == pred_turn:
        return 1.0
    gt_fns = [_fn_name(x) for x in gt_turn]
    pr_fns = [_fn_name(x) for x in pred_turn]
    if not gt_fns and not pr_fns:
        return 1.0
    if not gt_fns or not pr_fns:
        return 0.0

    gt_set = set(gt_fns)
    pr_set = set(pr_fns)
    inter = len(gt_set & pr_set)
    prec = inter / max(len(pr_set), 1)
    rec = inter / max(len(gt_set), 1)
    if prec + rec == 0:
        return 0.0
    return (2 * prec * rec) / (prec + rec)


def _soft_sequence_score(gt: list[list[str]], pred: list[list[str]]) -> float:
    """Aggregate soft score across turns."""
    if not gt and not pred:
        return 1.0
    n = max(len(gt), len(pred), 1)
    total = 0.0
    for i in range(n):
        gt_turn = gt[i] if i < len(gt) else []
        pr_turn = pred[i] if i < len(pred) else []
        total += _soft_turn_score(gt_turn, pr_turn)
    return total / n


def _diff_summary(gt: list[list[str]], pred: list[list[str]], max_turns: int = 8, max_calls_per_turn: int = 8) -> str:
    """Readable per-turn diff summary for GEPA feedback."""
    lines: list[str] = []
    n = min(max(len(gt), len(pred)), max_turns)
    for i in range(n):
        gt_turn = gt[i] if i < len(gt) else []
        pr_turn = pred[i] if i < len(pred) else []
        if gt_turn == pr_turn:
            lines.append(f"TURN {i+1}: OK (exact match)")
            continue

        lines.append(f"TURN {i+1}: MISMATCH")
        lines.append("  EXPECTED:")
        if gt_turn:
            for s in gt_turn[:max_calls_per_turn]:
                lines.append(f"    - {s}")
            if len(gt_turn) > max_calls_per_turn:
                lines.append(f"    ... (+{len(gt_turn) - max_calls_per_turn} more)")
        else:
            lines.append("    - (no calls expected)")

        lines.append("  GOT:")
        if pr_turn:
            for s in pr_turn[:max_calls_per_turn]:
                lines.append(f"    - {s}")
            if len(pr_turn) > max_calls_per_turn:
                lines.append(f"    ... (+{len(pr_turn) - max_calls_per_turn} more)")
        else:
            lines.append("    - (no calls produced)")
    if len(gt) != len(pred):
        lines.append(f"TURN COUNT: expected {len(gt)} turns, got {len(pred)} turns")
    return "\n".join(lines)


# -------------------------
# DSPy wrappers
# -------------------------


class BFCLExample(dspy.Example):
    def __init__(
        self,
        test_id: str | None = None,
        question: str | None = None,
        *,
        base: dspy.Example | None = None,
        **kwargs: Any,
    ):
        if base is not None:
            super().__init__(base=base, **kwargs)
        else:
            super().__init__(test_id=test_id, question=question, **kwargs)


class MetricFeedback(dspy.Prediction):
    def __init__(self, score: float, feedback: str) -> None:
        super().__init__(score=score, feedback=feedback)


class BFCLAgent(dspy.Module):
    """
    DSPy module wrapper around pytest-driven BFCL evaluation.
    The only optimized artifact is the instruction string stored in a DSPy Signature.
    """

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

        # This predictor exists so GEPA can optimize the `instructions` field.
        instruction_signature = dspy.Signature("prompt_input -> prompt_output", instructions=instruction_text)
        self.prompt_predictor = dspy.Predict(instruction_signature)

    def forward(self, test_id: str, question: str) -> dspy.Prediction:
        """
        Runs one BFCL test via pytest using the current instruction file.
        Returns enough artifacts for metrics to generate BFCL-aligned feedback.
        """
        # ---- Create a real DSPy trace anchor ----
        # We don't *use* the output; we just ensure the predictor is invoked so GEPA has a traced component.
        try:
            _ = self.prompt_predictor(prompt_input=question)
        except Exception:
            # If tracing fails due to LM issues, continue; pytest run is the true evaluator.
            pass

        instruction_text = self.get_instruction_text()
        self._instruction_path.write_text(instruction_text, encoding="utf-8")

        # Unique run dir avoids stale artifacts being reused across GEPA candidates.
        run_id = uuid.uuid4().hex[:12]
        output_dir = self.base_dir / "runs" / f"{test_id}__{run_id}"
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

        complete_path = output_dir / "raw" / f"{test_id}_complete.json"
        tool_calls_by_turn: list[list[dict[str, Any]]] = []
        executable_responses: list[list[str]] = []
        evaluation: dict[str, Any] | None = None
        eval_error: str | None = None

        if complete_path.exists():
            try:
                complete_data = json.loads(complete_path.read_text())
                tool_calls_by_turn = MessageSerializer.extract_tool_calls_by_turn(complete_data)
                executable_responses = MessageSerializer.format_to_executable(tool_calls_by_turn)
                evaluation = bfcl_evaluator._run_evaluation(test_id, tool_calls_by_turn, executable_responses)
            except Exception as e:
                eval_error = f"{type(e).__name__}: {e}"
        else:
            eval_error = "Complete JSON not found (agent may have crashed before serialization)."

        tools_used = [call.get("function") for turn in tool_calls_by_turn for call in turn if call.get("function")]
        behavior_summary = self._summarize_behavior_from_calls(tool_calls_by_turn)

        return dspy.Prediction(
            test_id=test_id,
            passed=passed,
            tools_used=tools_used,
            behavior=behavior_summary,
            executable_responses=executable_responses,
            evaluation=evaluation,
            eval_error=eval_error,
            pytest_stdout=result.stdout,
            pytest_stderr=result.stderr,
            run_dir=str(output_dir),
        )

    def get_instruction_text(self) -> str:
        instructions = getattr(self.prompt_predictor.signature, "instructions", "")
        if isinstance(instructions, (list, tuple)):
            return "\n".join(str(p) for p in instructions if p)
        return str(instructions or "")

    @staticmethod
    def _summarize_behavior_from_calls(tool_calls_by_turn: list[list[dict[str, Any]]]) -> str:
        tool_seq: list[str] = []
        for turn in tool_calls_by_turn:
            for call in turn:
                fn = call.get("function")
                if fn:
                    tool_seq.append(fn)
        return f"TOOLS: {' -> '.join(tool_seq) or 'NONE'}\nNUM_TOOLS: {len(tool_seq)}"


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
    """
    GEPA metric aligned to BFCL:
    - score is primarily BFCL validity (pass/fail), but we add a soft score component to provide gradient.
    - feedback includes BFCL evaluator diagnostics + per-turn executable diffs + constraint hints.
    """
    test_id = getattr(pred, "test_id", None) or getattr(gold, "test_id", None)
    feedback_parts: list[str] = []

    # Load BFCL truth + constraints for feedback
    gt: list[list[str]] = []
    excluded: list[str] = []
    involved_classes: list[str] = []
    try:
        if test_id:
            gt = bfcl_loader.load_ground_truth(test_id)
            entry = bfcl_loader.load_test_entry(test_id)
            excluded = entry.get("excluded_function", []) or []
            involved_classes = entry.get("involved_classes", []) or []
    except Exception as e:
        feedback_parts.append(f"WARNING: could not load BFCL ground truth/entry: {type(e).__name__}: {e}")

    pred_exec: list[list[str]] = getattr(pred, "executable_responses", []) or []
    evaluation: dict[str, Any] | None = getattr(pred, "evaluation", None)
    eval_error: str | None = getattr(pred, "eval_error", None)

    # Primary validity
    valid = False
    if evaluation and isinstance(evaluation, dict):
        try:
            valid = bool(evaluation.get("validation", {}).get("valid", False))
        except Exception:
            valid = False

    # Soft score for gradient (helps GEPA search)
    soft = _soft_sequence_score(gt, pred_exec) if gt else (1.0 if valid else 0.0)

    # Final score: keep pass/fail dominant, but allow soft improvements to be visible
    # This prevents GEPA from being totally flat when nothing flips to PASS yet.
    score = (1.0 if valid else 0.0) * 0.9 + soft * 0.1

    feedback_parts.append(f"RESULT: {'PASS' if valid else 'FAIL'}")
    feedback_parts.append(f"SCORE_BREAKDOWN: hard={'1.0' if valid else '0.0'} soft={soft:.3f} final={score:.3f}")

    if involved_classes:
        feedback_parts.append(f"INVOLVED_CLASSES (servers mounted): {', '.join(involved_classes)}")
    if excluded:
        feedback_parts.append(f"EXCLUDED_FUNCTIONS: {', '.join(excluded)}")

    # If we have evaluator info, surface the most relevant parts
    if evaluation and isinstance(evaluation, dict):
        validation = evaluation.get("validation", {})
        irrelevance = evaluation.get("irrelevance_check", {})
        feedback_parts.append("EVALUATOR_VALIDATION:")
        # Keep it compact; GEPA reflection needs signal, not a huge JSON blob.
        if isinstance(validation, dict):
            # Include key flags + common fields if present
            for k in ["valid", "reason", "error_type", "error_message"]:
                if k in validation:
                    feedback_parts.append(f"  {k}: {validation.get(k)}")
        else:
            feedback_parts.append(f"  validation: {validation}")

        if isinstance(irrelevance, dict) and irrelevance:
            feedback_parts.append("EVALUATOR_IRRELEVANCE_CHECK:")
            for k in ["is_irrelevant", "reason"]:
                if k in irrelevance:
                    feedback_parts.append(f"  {k}: {irrelevance.get(k)}")

    if eval_error:
        feedback_parts.append(f"EVAL_ERROR: {eval_error}")

    # Per-turn executable diff is the strongest actionable feedback
    if gt:
        feedback_parts.append("EXECUTABLE_DIFF:")
        feedback_parts.append(_diff_summary(gt, pred_exec))

    # Constraint violation hint: excluded function used
    if excluded and pred_exec:
        used_fns = {_fn_name(s) for turn in pred_exec for s in turn}
        bad = sorted(set(excluded) & used_fns)
        if bad:
            feedback_parts.append(f"CONSTRAINT_VIOLATION: used excluded function(s): {', '.join(bad)}")

    # Light behavior summary
    if hasattr(pred, "behavior"):
        feedback_parts.append("BEHAVIOR_SUMMARY:")
        feedback_parts.append(str(pred.behavior))

    # Where artifacts live (useful for debugging candidate runs)
    run_dir = getattr(pred, "run_dir", None)
    if run_dir:
        feedback_parts.append(f"RUN_DIR: {run_dir}")

    return MetricFeedback(score=score, feedback="\n".join(feedback_parts))


# -------------------------
# Data loading
# -------------------------


def load_test_cases(subset: str, limit: int) -> list[BFCLExample]:
    test_ids = bfcl_loader.find_tests_in_category(subset, limit=limit)
    examples: list[BFCLExample] = []
    for test_id in test_ids[:limit]:
        entry = bfcl_loader.load_test_entry(test_id)
        question = _stringify_question(entry.get("question", ""))
        ex = BFCLExample(test_id=test_id, question=question)
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
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/gepa_on_bfcl"))
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

    # Baseline (use BFCL evaluator validity when available, not pytest returncode alone)
    baseline_valid = 0
    baseline_total = len(examples)
    baseline_details: list[dict[str, Any]] = []

    for e in examples:
        pred = agent(test_id=e.test_id, question=e.question)
        valid = False
        if getattr(pred, "evaluation", None):
            valid = bool(pred.evaluation.get("validation", {}).get("valid", False))
        else:
            valid = bool(getattr(pred, "passed", False))
        baseline_valid += 1 if valid else 0
        baseline_details.append(
            {
                "test_id": e.test_id,
                "valid": valid,
                "run_dir": getattr(pred, "run_dir", None),
                "eval_error": getattr(pred, "eval_error", None),
            }
        )

    baseline_score = baseline_valid / max(baseline_total, 1)
    (args.output_dir / "baseline.json").write_text(
        json.dumps(
            {
                "instruction_hash": instruction_hash,
                "bfcl_valid_rate": baseline_score,
                "valid": baseline_valid,
                "total": baseline_total,
                "test_ids": [e.test_id for e in examples],
                "model": args.model,
                "runs": baseline_details,
            },
            indent=2,
        )
    )

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
        "baseline_bfcl_valid_rate": baseline_score,
        "final_score": max(results.val_aggregate_scores) if results.val_aggregate_scores else None,
        "total_metric_calls": results.total_metric_calls,
        "num_full_val_evals": results.num_full_val_evals,
        "seed": results.seed,
    }
    (args.output_dir / "optimization_metadata.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
