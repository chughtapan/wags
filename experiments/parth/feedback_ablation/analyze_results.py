#!/usr/bin/env python3
"""Analysis pipeline for feedback experiment results.

Reads external_feedback.jsonl, *_evaluation.json, and *_complete.json across
all cells and produces:
  1. A results dataframe (one row per subset × condition × test_case_id)
  2. Recovery rate table by (subset, condition)
  3. Disruption rate table by (subset, condition) over consistent_pass cases
  4. Behavioral response distribution by condition
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parent.parent.parent
FEEDBACK_DIR = REPO_ROOT / "outputs" / "feedback"
BASELINE_STABILITY_YAML = _THIS_DIR / "baseline_stability.yaml"
CASES_YAML = _THIS_DIR / "cases.yaml"

CONDITIONS = ["specific", "vague", "verbose", "null"]
BASELINES = ["baseline_1", "baseline_2", "baseline_3"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_baseline_outcomes() -> dict[tuple[str, str], str]:
    """Load (subset, case_id) -> stability from baseline_stability.yaml."""
    with open(BASELINE_STABILITY_YAML) as f:
        entries = yaml.safe_load(f)
    return {
        (e["subset"], e["case_id"]): e["baseline_stability"]
        for e in entries
    }


def load_expected_cases() -> dict[str, list[str]]:
    """Load subset -> [case_ids] from cases.yaml."""
    with open(CASES_YAML) as f:
        cases = yaml.safe_load(f)
    by_subset: dict[str, list[str]] = {}
    for c in cases:
        by_subset.setdefault(c["subset"], []).append(c["case_id"])
    return by_subset


def load_feedback_log(path: Path) -> dict[str, list[dict]]:
    """Parse external_feedback.jsonl, return {test_case_id: [records]}."""
    by_case: dict[str, list[dict]] = defaultdict(list)
    if not path.exists():
        return by_case
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                by_case[r["test_case_id"]].append(r)
    return by_case


def _run_eval_from_complete(test_id: str, complete_path: Path) -> dict | None:
    """Run BFCL evaluation from a complete.json file. Returns eval dict or None."""
    try:
        from tests.benchmarks.bfcl.test_bfcl import _validate_from_complete_json
        return _validate_from_complete_json(test_id, complete_path)
    except Exception:
        return None


def find_eval_result(cell_dir: Path, case_id: str) -> str | None:
    """Find evaluation result for a case. Returns 'pass', 'fail', or None.

    If no evaluation file exists but a complete.json does, retroactively
    evaluates from the complete.json and caches the result.
    """
    # Check raw/ directory (feedback runs)
    candidates = [
        cell_dir / "raw" / f"{case_id}_evaluation.json",
        # Baseline format: per-case subdirectory
        cell_dir / case_id / "evaluation.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                ev = json.load(f)
            valid = ev.get("validation", {}).get("valid", False)
            return "pass" if valid else "fail"

    # No eval file — try retroactive evaluation from complete.json
    complete_path = find_complete_json(cell_dir, case_id)
    if complete_path is not None and complete_path.exists():
        ev = _run_eval_from_complete(case_id, complete_path)
        if ev is not None:
            # Cache the result
            eval_out = complete_path.parent / f"{case_id}_evaluation.json"
            eval_out.write_text(json.dumps(ev, indent=2, default=str))
            valid = ev.get("validation", {}).get("valid", False)
            return "pass" if valid else "fail"

    return None


def find_complete_json(cell_dir: Path, case_id: str) -> Path | None:
    """Find complete.json for a case."""
    candidates = [
        cell_dir / "raw" / f"{case_id}_complete.json",
        cell_dir / case_id / "raw" / f"{case_id}_complete.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def classify_behavior(
    complete_path: Path | None,
    feedback_records: list[dict],
) -> str:
    """Classify agent behavior after feedback.

    Returns one of:
      not_triggered, identical_retry, different_args, different_tool,
      no_retry, reasoning_shown, crash
    """
    triggered = [r for r in feedback_records if r.get("triggered")]
    if not triggered:
        return "not_triggered"

    if complete_path is None or not complete_path.exists():
        return "crash"

    with open(complete_path) as f:
        data = json.load(f)
    msgs = data.get("messages", [])

    # Collect all feedback messages for matching
    feedback_texts = [r["feedback_message"] for r in triggered if r.get("feedback_message")]

    behaviors = []

    for i, msg in enumerate(msgs):
        tr = msg.get("tool_results") or {}
        for tid, result in tr.items():
            texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
            full_text = " ".join(texts)

            is_feedback = any(ft and ft[:40] in full_text for ft in feedback_texts)
            if not is_feedback:
                continue

            # Find original call
            orig_call = None
            if i > 0:
                prev = msgs[i - 1]
                for ptid, pcall in (prev.get("tool_calls") or {}).items():
                    if ptid == tid:
                        orig_call = pcall
                        break

            # Check next assistant message
            if i + 1 >= len(msgs):
                behaviors.append("no_retry")
                continue

            nxt = msgs[i + 1]
            if nxt.get("role") != "assistant":
                behaviors.append("no_retry")
                continue

            has_reasoning = any(
                (isinstance(c, dict) and c.get("text", "").strip())
                or (isinstance(c, str) and c.strip())
                for c in (nxt.get("content") or [])
            )

            next_calls = nxt.get("tool_calls") or {}

            if not next_calls:
                behaviors.append("reasoning_shown" if has_reasoning else "no_retry")
                continue

            if orig_call:
                orig_name = orig_call["name"]
                orig_args = orig_call.get("arguments")
                retry_same = [c for c in next_calls.values() if c["name"] == orig_name]
                if retry_same:
                    if retry_same[0].get("arguments") == orig_args:
                        behaviors.append("reasoning_shown" if has_reasoning else "identical_retry")
                    else:
                        behaviors.append("reasoning_shown" if has_reasoning else "different_args")
                else:
                    behaviors.append("reasoning_shown" if has_reasoning else "different_tool")
            else:
                behaviors.append("reasoning_shown" if has_reasoning else "different_tool")

    if not behaviors:
        return "not_triggered"

    # Priority: reasoning_shown > different_tool > different_args > no_retry > identical_retry
    priority = ["reasoning_shown", "different_tool", "different_args", "no_retry", "identical_retry"]
    for p in priority:
        if p in behaviors:
            return p
    return behaviors[0]


# ---------------------------------------------------------------------------
# Build results dataframe
# ---------------------------------------------------------------------------

def build_results() -> list[dict]:
    baseline_outcomes = load_baseline_outcomes()
    expected_cases = load_expected_cases()
    rows = []

    for subset, case_ids in sorted(expected_cases.items()):
        for condition in CONDITIONS:
            cell_dir = FEEDBACK_DIR / subset / condition
            if not cell_dir.exists():
                continue

            feedback_log = load_feedback_log(cell_dir / "raw" / "external_feedback.jsonl")

            for case_id in sorted(case_ids):
                fb_records = feedback_log.get(case_id, [])
                triggered = [r for r in fb_records if r.get("triggered")]

                eval_result = find_eval_result(cell_dir, case_id)
                complete_path = find_complete_json(cell_dir, case_id)

                behavior = classify_behavior(complete_path, fb_records)

                # Determine evaluator outcome
                if eval_result is not None:
                    eval_outcome = eval_result
                elif complete_path and complete_path.exists():
                    eval_outcome = "crash"  # ran but no eval = likely crashed
                else:
                    eval_outcome = "missing"

                rows.append({
                    "subset": subset,
                    "condition": condition,
                    "case_id": case_id,
                    "baseline_outcome": baseline_outcomes.get((subset, case_id), "unknown"),
                    "trigger_fired": len(triggered) > 0,
                    "trigger_count": len(triggered),
                    "behavioral_response": behavior,
                    "evaluator_outcome": eval_outcome,
                })

    return rows


# ---------------------------------------------------------------------------
# Summary tables
# ---------------------------------------------------------------------------

def print_table(headers: list[str], rows: list[list], title: str) -> None:
    """Print a formatted table."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def compute_baseline_eval(subset: str, case_id: str) -> dict[str, str | None]:
    """Get pass/fail from each baseline run."""
    results = {}
    for bl in BASELINES:
        cell_dir = FEEDBACK_DIR / subset / bl
        results[bl] = find_eval_result(cell_dir, case_id)
    return results


def table_accuracy(results: list[dict]) -> None:
    """Overall accuracy by (subset, condition) vs. baseline."""
    expected_cases = load_expected_cases()
    headers = ["subset", "condition", "n_cases", "n_pass", "n_fail", "n_other", "accuracy", "baseline_accuracy"]
    table_rows = []

    total_pass = 0
    total_cases = 0
    bl_total_pass = 0
    bl_total_runs = 0

    for subset in sorted(set(r["subset"] for r in results)):
        case_ids = expected_cases.get(subset, [])

        # Baseline accuracy for this subset (averaged across 3 runs)
        bl_passes = 0
        bl_runs = 0
        for case_id in case_ids:
            bl_results = compute_baseline_eval(subset, case_id)
            for outcome in bl_results.values():
                if outcome is not None:
                    bl_runs += 1
                    if outcome == "pass":
                        bl_passes += 1
        bl_acc = f"{bl_passes}/{bl_runs} ({100 * bl_passes / bl_runs:.0f}%)" if bl_runs > 0 else "—"
        bl_total_pass += bl_passes
        bl_total_runs += bl_runs

        for condition in CONDITIONS:
            cell = [r for r in results if r["subset"] == subset and r["condition"] == condition]
            if not cell:
                continue
            n = len(cell)
            n_pass = sum(1 for r in cell if r["evaluator_outcome"] == "pass")
            n_fail = sum(1 for r in cell if r["evaluator_outcome"] == "fail")
            n_other = n - n_pass - n_fail
            acc = f"{n_pass}/{n} ({100 * n_pass / n:.0f}%)"
            table_rows.append([subset, condition, n, n_pass, n_fail, n_other, acc, bl_acc])
            total_pass += n_pass
            total_cases += n

    print_table(headers, table_rows, "Table 0: Overall Accuracy by (Subset, Condition)")

    bl_pct = 100 * bl_total_pass / bl_total_runs if bl_total_runs else 0
    by_cond: dict[str, tuple[int, int]] = {}
    for condition in CONDITIONS:
        cond_rows = [r for r in results if r["condition"] == condition]
        cp = sum(1 for r in cond_rows if r["evaluator_outcome"] == "pass")
        cn = len(cond_rows)
        by_cond[condition] = (cp, cn)
    parts = " | ".join(
        f"{c}: {p}/{n} ({100 * p / n:.1f}%)" for c, (p, n) in by_cond.items() if n
    )
    print(f"\nBaseline accuracy: {bl_total_pass}/{bl_total_runs} ({bl_pct:.1f}%)")
    print(f"Feedback accuracy — {parts}")


def table_recovery(results: list[dict]) -> None:
    """Recovery rate by (subset, condition), split by baseline category."""
    # Group: for consistent_fail and flaky cases, what fraction passed under feedback?
    headers = ["subset", "condition", "baseline_cat", "n_cases", "n_pass", "n_fail", "n_crash", "recovery_rate"]
    table_rows = []

    for baseline_cat in ["consistent_fail", "flaky"]:
        for subset in sorted(set(r["subset"] for r in results)):
            for condition in CONDITIONS:
                cell = [
                    r for r in results
                    if r["subset"] == subset
                    and r["condition"] == condition
                    and r["baseline_outcome"] == baseline_cat
                ]
                if not cell:
                    continue
                n = len(cell)
                n_pass = sum(1 for r in cell if r["evaluator_outcome"] == "pass")
                n_fail = sum(1 for r in cell if r["evaluator_outcome"] == "fail")
                n_crash = sum(1 for r in cell if r["evaluator_outcome"] in ("crash", "missing"))
                rate = f"{n_pass}/{n} ({100 * n_pass / n:.0f}%)" if n > 0 else "—"
                table_rows.append([subset, condition, baseline_cat, n, n_pass, n_fail, n_crash, rate])

    # Add baseline column: aggregate pass rate across 3 baseline runs
    headers_with_bl = headers + ["baseline_pass_rate"]
    table_rows_with_bl = []
    expected_cases = load_expected_cases()

    for row in table_rows:
        subset, condition, baseline_cat = row[0], row[1], row[2]
        case_ids = [
            r["case_id"] for r in results
            if r["subset"] == subset
            and r["condition"] == condition
            and r["baseline_outcome"] == baseline_cat
        ]
        bl_passes = 0
        bl_total = 0
        for case_id in case_ids:
            bl_results = compute_baseline_eval(subset, case_id)
            for bl, outcome in bl_results.items():
                if outcome is not None:
                    bl_total += 1
                    if outcome == "pass":
                        bl_passes += 1
        bl_rate = f"{bl_passes}/{bl_total} ({100 * bl_passes / bl_total:.0f}%)" if bl_total > 0 else "—"
        table_rows_with_bl.append(row + [bl_rate])

    print_table(headers_with_bl, table_rows_with_bl, "Table 1: Recovery Rate (consistent_fail & flaky cases)")


def table_disruption(results: list[dict]) -> None:
    """Disruption rate over consistent_pass cases where feedback fired."""
    headers = ["subset", "condition", "n_cases", "n_triggered", "n_pass", "n_fail", "n_crash", "disruption_rate"]
    table_rows = []

    for subset in sorted(set(r["subset"] for r in results)):
        for condition in CONDITIONS:
            cell = [
                r for r in results
                if r["subset"] == subset
                and r["condition"] == condition
                and r["baseline_outcome"] == "consistent_pass"
            ]
            if not cell:
                continue
            n = len(cell)
            n_triggered = sum(1 for r in cell if r["trigger_fired"])
            n_pass = sum(1 for r in cell if r["evaluator_outcome"] == "pass")
            n_fail = sum(1 for r in cell if r["evaluator_outcome"] == "fail")
            n_crash = sum(1 for r in cell if r["evaluator_outcome"] in ("crash", "missing"))
            disrupted = n_fail + n_crash
            rate = f"{disrupted}/{n} ({100 * disrupted / n:.0f}%)" if n > 0 else "—"
            table_rows.append([subset, condition, n, n_triggered, n_pass, n_fail, n_crash, rate])

    print_table(headers, table_rows, "Table 2: Disruption Rate (consistent_pass cases)")


def table_behavior(results: list[dict]) -> None:
    """Behavioral response distribution by condition (pooled across subsets)."""
    behavior_types = [
        "not_triggered", "identical_retry", "different_args",
        "different_tool", "no_retry", "reasoning_shown", "crash",
    ]
    headers = ["condition", "n_total"] + behavior_types

    table_rows = []
    for condition in CONDITIONS:
        cell = [r for r in results if r["condition"] == condition]
        n = len(cell)
        counts = {b: sum(1 for r in cell if r["behavioral_response"] == b) for b in behavior_types}
        row = [condition, n] + [counts.get(b, 0) for b in behavior_types]
        table_rows.append(row)

    print_table(headers, table_rows, "Table 3: Behavioral Response Distribution by Condition (pooled)")

    # Also by (subset, condition)
    headers2 = ["subset", "condition", "n_total"] + behavior_types
    table_rows2 = []
    for subset in sorted(set(r["subset"] for r in results)):
        for condition in CONDITIONS:
            cell = [r for r in results if r["subset"] == subset and r["condition"] == condition]
            if not cell:
                continue
            n = len(cell)
            counts = {b: sum(1 for r in cell if r["behavioral_response"] == b) for b in behavior_types}
            row = [subset, condition, n] + [counts.get(b, 0) for b in behavior_types]
            table_rows2.append(row)

    print_table(headers2, table_rows2, "Table 3b: Behavioral Response Distribution by (Subset, Condition)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    results = build_results()

    # Print full dataframe
    print(f"Results dataframe: {len(results)} rows")
    print(f"Subsets: {sorted(set(r['subset'] for r in results))}")
    print(f"Conditions: {sorted(set(r['condition'] for r in results))}")

    # Dump dataframe as CSV
    csv_path = _THIS_DIR / "results_dataframe.csv"
    fieldnames = [
        "subset", "condition", "case_id", "baseline_outcome",
        "trigger_fired", "trigger_count", "behavioral_response", "evaluator_outcome",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nDataframe written to {csv_path}")

    # Summary tables
    table_accuracy(results)
    table_recovery(results)
    table_disruption(results)
    table_behavior(results)


if __name__ == "__main__":
    main()
