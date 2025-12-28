""""
scoring_utils.py

Utility functions used for evaluating a BFCL agent's tool use
"""

from __future__ import annotations
from typing import List


def fn_name(executable_call: str) -> str:
    """
    Extract the function name from a tool call string
    
    Ex: read(file='log.txt') -> 'read'
    """
    if not executable_call:
        return ""
    
    i = executable_call.index("(")
    return executable_call[:i] if i != -1 else executable_call


def soft_turn_score(gt_turn: List[str], pred_turn: List[str]) -> float:
    """
    Returns a score in [0, 1] for a single turn by comparing function
    overlap between ground truth and agent prediction
    """
    # Perfectly aligned
    if gt_turn == pred_turn:
        return 1.0
    
    gt_fns = [fn_name(x) for x in gt_turn]
    pr_fns = [fn_name(x) for x in pred_turn]
    
    # No functions expected AND no functions called
    if not gt_fns and not pr_fns:
        return 1.0
    
    # Either:
    # No functions were expected but agent still called some
    # OR agent didn't call any functions when it was expected to
    if not gt_fns or not pr_fns:
        return 0.0
    
    gt_set = set(gt_fns)
    pr_set = set(pr_fns)
    intersection = len(gt_set.intersection(pr_set))
    
    # No tool intersection -> 0.0
    if intersection == 0:
        return 0.0
    
    # Of all the tools the agent called, how many were in G.T
    precision = intersection / max(len(pr_set), 1)
    # Of all the tools in GT, how many did the agent call
    recall = intersection / max(len(gt_set), 1) 
    
    # F1 Score = harmonic mean of precision and recall
    # Higher F1 = high prec AND high rec
    # Lower F1 = low prec and rec OR extreme difference btwn them
    return (2 * precision * recall) / (precision + recall)
    

def soft_sequence_score(gt: List[List[str]], pred: List[List[str]]) -> float:
    """
    Returns a score in [0, 1] for a given multi-turn sequence, which is the
    arithmetic average of soft turn scores
    """
    # No functions expected AND no functions called
    if not gt and not pred:
        return 1.0
    
    n = max(len(gt), len(pred), 1)
    total = 0.0
    
    for i in range(n):
        gt_turn = gt[i] if i < len(gt) else []
        pred_turn = pred[i] if i < len(pred) else []
        
        # Add up each turn's F1 Score
        total += soft_turn_score(gt_turn, pred_turn)
        
    # Return average
    return total / n


def diff_summary(gt: List[List[str]], pred: List[List[str]], 
                *, max_turns: int = 8, max_calls_per_turn: int = 8
                ) -> str:
    """
    Produce a readable string representation of the diff between
    GT and predicted tool call sequences

    Intended for logging
    """
    lines: List[str] = []
    n = min(max(len(gt), len(pred)), max_turns)
    
    for i in range(n):
        gt_turn = gt[i] if i < len(gt) else []
        pr_turn = pred[i] if i < len(pred) else []

        if gt_turn == pr_turn:
            lines.append(f"TURN {i + 1}: OK (exact match)")
            continue

        lines.append(f"TURN {i + 1}: MISMATCH")
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
        lines.append(
            f"TURN COUNT: expected {len(gt)} turns, got {len(pred)} turns"
        )

    return "\n".join(lines)