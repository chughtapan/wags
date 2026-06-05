"""
metrics.py

Metric and feedback for GEPA optimization on BFCL
"""

from __future__ import annotations
from typing import Any, Optional, List
import dspy
from tests.benchmarks.bfcl import loader as bfcl_loader
from . import logging_utils
from .logging_utils import append_jsonl, safe_json, utc_now_iso
from .scoring_utils import fn_name, soft_sequence_score, diff_summary


class MetricFeedback(dspy.Prediction):
    """
    Prediction returned to GEPA containing a scalar score and
    human-readable feedback
    """
    
    def __init__(self, score: float, feedback: str):
        super().__init__(score=score, feedback=feedback)


def build_score_definition() -> dict[str, Any]:
    return {
        "hard_valid": "BFCL evaluator validation.valid (boolean) from multi_turn_checker",
        "final": "1.0 if hard_valid else 0.0",
        "note": (
            "Optimization and candidate scores use only hard validity. "
            "No soft or shaping score is applied."
        )
    }
  
    
def bfcl_metric_with_feedback(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Optional[Any] = None,
    pred_name: Optional[str] = None,
    pred_trace: Optional[Any] = None
) -> MetricFeedback:
    """
    Computes the GEPA metric for a single BFCL evaluation.
    Returns MetricFeedback(score, feedback)
    """
    # Extract test id and initialize feedback
    test_id = getattr(pred, "test_id", None) or getattr(gold, "test_id", None)
    feedback_parts: List[str] = []
    ctx = logging_utils.RUN_CTX
    
    if ctx is None:
        raise RuntimeError(
            "RUN_CTX is None inside bfcl_metric_with_feedback. "
            "This means run.py did not initialize logging_utils.RUN_CTX correctly."
        )

    
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
        feedback_parts.append(
            f"WARNING: could not load BFCL ground truth/entry: {type(e).__name__}: {e}"
        )
    
    # Pull prediction info
    pred_exec: list[list[str]] = getattr(pred, "executable_responses", []) or []
    evaluation: dict[str, Any] | None = getattr(pred, "evaluation", None)
    eval_error: str | None = getattr(pred, "eval_error", None)
    
    # Compute hard-valid (pass/fail)
    hard_valid = False
    if evaluation and isinstance(evaluation, dict):
        hard_valid = bool(evaluation.get("validation", {}).get("valid", False))
        
    # Final score
    final_score = 1.0 if hard_valid else 0.0

    
    # Train/dev split
    split = None
    if ctx and test_id:
        if ctx.train_ids and test_id in ctx.train_ids:
            split = "train"
        elif ctx.dev_ids and test_id in ctx.dev_ids:
            split = "dev"
        else:
            split = "unknown"
            
    feedback_parts.append(f"RESULT: {'PASS' if hard_valid else 'FAIL'}")
    feedback_parts.append(
        f"SCORE: {'1.0' if hard_valid else '0.0'} (hard_valid)"
    )
    if split:
        feedback_parts.append(f"SPLIT: {split}")
        
    # if involved_classes:
    #     feedback_parts.append(f"INVOLVED_CLASSES (servers mounted): {', '.join(involved_classes)}")
    # if excluded:
    #     feedback_parts.append(f"EXCLUDED_FUNCTIONS: {', '.join(excluded)}")

    if evaluation and isinstance(evaluation, dict):
        validation = evaluation.get("validation", {})
        irrelevance = evaluation.get("irrelevance_check", {})
        feedback_parts.append("EVALUATOR_VALIDATION:")
        if isinstance(validation, dict):
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

    if gt:
        feedback_parts.append("EXECUTABLE_DIFF:")
        feedback_parts.append(diff_summary(gt, pred_exec))

    if excluded and pred_exec:
        used_fns = {fn_name(s) for turn in pred_exec for s in turn}
        bad = sorted(set(excluded) & used_fns)
        # if bad:
        #     feedback_parts.append(f"CONSTRAINT_VIOLATION: used excluded function(s): {', '.join(bad)}")

    if hasattr(pred, "behavior"):
        feedback_parts.append("BEHAVIOR_SUMMARY:")
        feedback_parts.append(str(pred.behavior))

    run_dir = getattr(pred, "run_dir", None)
    if run_dir:
        feedback_parts.append(f"RUN_DIR: {run_dir}")

    # Log the record
    if ctx and test_id:
        record = {
            "ts": utc_now_iso(),
            "run_id": ctx.run_id,
            "test_id": test_id,
            "split": split,
            "instruction_hash": getattr(pred, "instruction_hash", None),
            "hard_valid": hard_valid,
            "final": final_score,
            "timing": getattr(pred, "timing", None),
            "run_dir": run_dir,
            "eval_error": eval_error,
            "evaluator_validation": (
                safe_json(evaluation.get("validation"))
                if isinstance(evaluation, dict)
                else None
            ),
            "evaluator_irrelevance": (
                safe_json(evaluation.get("irrelevance_check"))
                if isinstance(evaluation, dict)
                else None
            ),
        }
        append_jsonl(ctx.metric_calls_path, record)
        
        # Candidate snapshot
        snap = {
            "ts": utc_now_iso(),
            "run_id": ctx.run_id,
            "instruction_hash": getattr(pred, "instruction_hash", None),
            "instruction_text": getattr(pred, "instruction_text", None),
            "latest_eval": {
                "test_id": test_id,
                "split": split,
                "hard_valid": hard_valid,
                "final": final_score,
            },
        }
        append_jsonl(ctx.candidate_snapshots_path, snap)
        
    return MetricFeedback(score=final_score, feedback="\n".join(feedback_parts))