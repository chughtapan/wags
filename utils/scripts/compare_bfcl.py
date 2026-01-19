"""Compare BFCL run outputs by re-running the evaluator on complete logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal, NamedTuple
from tests.benchmarks.bfcl import evaluator
from tests.utils.fastagent_helpers import MessageSerializer
import traceback

Status = Literal["PASS", "FAIL"]


class RunResult(NamedTuple):
    test_id: str
    status: Status
    details: dict[str, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare BFCL run logs.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("outputs/baseline_multi_turn_base/raw"),
        help="Directory containing baseline *_complete.json files.",
    )
    parser.add_argument(
        "--new",
        type=Path,
        default=Path("outputs/new_multi_turn_base/raw"),
        help="Directory containing new *_complete.json files.",
    )
    return parser.parse_args()


def evaluate_complete(test_id: str, complete_path: Path) -> RunResult | None:
    """Run BFCL evaluation on a complete.json file."""
    if not complete_path.exists():
        return None

    try:
        with complete_path.open("r", encoding="utf-8") as f:
            complete_data = json.load(f)

        tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
        executable = MessageSerializer.format_to_executable(tool_calls)

        # Run evaluation the same way the pytest harness does. If evaluator raises,
        # capture the exception and treat the test as a FAIL so totals match pytest.
        try:
            evaluation = evaluator._run_evaluation(test_id, tool_calls, executable)
            status: Status = "PASS" if evaluation.get("validation", {}).get("valid") else "FAIL"
            return RunResult(test_id, status, evaluation)
        except Exception as eval_exc:
            # Return a failing RunResult with diagnostic details instead of None
            tb = traceback.format_exc()
            details = {"error": str(eval_exc), "traceback": tb}
            return RunResult(test_id, "FAIL", details)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[WARN] Failed to evaluate {complete_path}: {exc}")
        # Provide more context for debugging
        try:
            print("--- Debug info ---")
            print(f"test_id={test_id}")
            if 'complete_data' in locals():
                msgs = complete_data.get('messages') if isinstance(complete_data, dict) else None
                print(f"message_count={len(msgs) if msgs is not None else 'N/A'}")
                # show first assistant message tool_calls sample
                if msgs:
                    for m in msgs[:10]:
                        if m.get('tool_calls'):
                            print('sample_tool_calls=', list(m.get('tool_calls').items())[:1])
                            break
        except Exception:
            pass
        traceback.print_exc()
        # If we couldn't even parse the file, mark as FAIL with diagnostics
        tb = traceback.format_exc()
        details = {"error": str(exc), "traceback": tb}
        return RunResult(test_id, "FAIL", details)


def collect_results(root: Path) -> dict[str, RunResult]:
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    results: dict[str, RunResult] = {}
    for complete_path in sorted(root.glob("*_complete.json")):
        test_id = complete_path.stem.replace("_complete", "")
        evaluated = evaluate_complete(test_id, complete_path)
        if evaluated:
            results[test_id] = evaluated
    return results


def main() -> None:
    args = parse_args()

    baseline = collect_results(args.baseline)
    new = collect_results(args.new)

    all_test_ids = sorted(set(baseline) | set(new))

    improvements: list[str] = []
    regressions: list[str] = []
    unchanged: list[str] = []
    missing_in_new: list[str] = []
    missing_in_baseline: list[str] = []

    for test_id in all_test_ids:
        baseline_result = baseline.get(test_id)
        new_result = new.get(test_id)

        if baseline_result is None and new_result is None:
            continue
        if baseline_result is None:
            missing_in_baseline.append(test_id)
            continue
        if new_result is None:
            missing_in_new.append(test_id)
            continue

        if baseline_result.status == "FAIL" and new_result.status == "PASS":
            improvements.append(test_id)
        elif baseline_result.status == "PASS" and new_result.status == "FAIL":
            regressions.append(test_id)
        elif baseline_result.status == new_result.status:
            unchanged.append(test_id)

    print("\n===== BFCL Log Comparison =====\n")
    print(f"Baseline dir: {args.baseline}")
    print(f"New dir:      {args.new}\n")

    print(f"Total baseline logs: {len(baseline)}")
    print(f"Total new logs:      {len(new)}")
    # Print PASS/FAIL totals for each run to aid comparison with pytest output
    baseline_pass = sum(1 for r in baseline.values() if r.status == "PASS")
    baseline_fail = sum(1 for r in baseline.values() if r.status == "FAIL")
    new_pass = sum(1 for r in new.values() if r.status == "PASS")
    new_fail = sum(1 for r in new.values() if r.status == "FAIL")
    print(f"Baseline PASS/FAIL:  {baseline_pass} passed, {baseline_fail} failed")
    print(f"New PASS/FAIL:       {new_pass} passed, {new_fail} failed")
    print(f"Shared evaluations:  {len(all_test_ids) - len(missing_in_baseline) - len(missing_in_new)}")
    print(f"Improvements (FAIL → PASS): {len(improvements)}")
    print(f"Regressions (PASS → FAIL): {len(regressions)}")
    print(f"Unchanged (same result):   {len(unchanged)}")
    print(f"Missing in new run:        {len(missing_in_new)}")
    print(f"Missing in baseline run:   {len(missing_in_baseline)}\n")

    if improvements:
        print("=== Improvements ===")
        for test_id in improvements:
            print(f"  - {test_id}")

    if regressions:
        print("\n=== Regressions ===")
        for test_id in regressions:
            print(f"  - {test_id}")

    if missing_in_new:
        print("\n=== Missing in New Run ===")
        for test_id in missing_in_new:
            print(f"  - {test_id}")

    if missing_in_baseline:
        print("\n=== Missing in Baseline Run ===")
        for test_id in missing_in_baseline:
            print(f"  - {test_id}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
