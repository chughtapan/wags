#!/usr/bin/env python3
"""
Script to run BFCL multi-turn test cases and evaluate them.
Usage: python run_bfcl_multi_turn.py --category multi_turn_base --model gpt-4o-mini [--start 0] [--end 200]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from src.elicitation_evals.bfcl.data_loader import find_tests_in_category


def run_test(test_id: str, model: str) -> Dict[str, Any]:
    """Run a single test case."""
    print(f"\n{'='*60}")
    print(f"Running test: {test_id}")
    print(f"{'='*60}")
    
    result = {
        "test_id": test_id,
        "status": "pending",
        "error": None,
        "passed": False
    }
    
    try:
        # Run the test
        cmd = ["elicitation-evals", "test", test_id, "--model", model]
        print(f"Command: {' '.join(cmd)}")
        
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per test
        )
        
        if process.returncode != 0:
            result["status"] = "failed"
            result["error"] = f"Test failed: {process.stderr}"
            print(f"❌ Test execution failed: {process.stderr}")
            return result
        
        # Run evaluation
        log_file = Path(f"outputs/raw/{test_id}_fastagent.jsonl")
        if not log_file.exists():
            result["status"] = "failed"
            result["error"] = f"Log file not found: {log_file}"
            print(f"❌ Log file not found: {log_file}")
            return result
        
        eval_cmd = ["elicitation-evals", "evaluate", test_id, str(log_file)]
        print(f"Evaluating: {' '.join(eval_cmd)}")
        
        eval_process = subprocess.run(
            eval_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if eval_process.returncode != 0:
            result["status"] = "eval_failed"
            result["error"] = f"Evaluation failed: {eval_process.stderr}"
            print(f"⚠️  Evaluation failed: {eval_process.stderr}")
        else:
            # Check if test passed from evaluation JSON file
            eval_file = Path(f"outputs/evaluations/{test_id}.json")
            if eval_file.exists():
                with open(eval_file) as f:
                    eval_data = json.load(f)
                    if eval_data.get("validation", {}).get("valid", False):
                        result["status"] = "passed"
                        result["passed"] = True
                        print("✅ Test passed!")
                    else:
                        result["status"] = "failed"
                        result["passed"] = False
                        print("❌ Test failed evaluation")
            else:
                result["status"] = "failed"
                result["passed"] = False
                print("❌ Evaluation file not found")
        
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "Test execution timed out"
        print("⏱️  Test timed out")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"💥 Unexpected error: {e}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Run BFCL multi-turn test cases")
    
    # Supported multi-turn categories
    valid_categories = ["multi_turn_base", "multi_turn_long_context"]
    
    parser.add_argument("--category", required=True, choices=valid_categories,
                        help="Test category to run (multi_turn_base or multi_turn_long_context)")
    parser.add_argument("--model", required=True, help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--start", type=int, default=0, help="Start index (default: 0)")
    parser.add_argument("--end", type=int, help="End index (default: all)")
    parser.add_argument("--continue-on-error", action="store_true", 
                        help="Continue running tests even if some fail")
    args = parser.parse_args()
    
    # Find all test cases
    print(f"Finding all {args.category} test cases...")
    all_tests = find_tests_in_category(args.category)
    all_tests = sorted(all_tests)  # Sort for consistent ordering
    
    # Set default end based on category size
    if args.end is None:
        args.end = len(all_tests)
    
    # Apply range filter
    tests_to_run = all_tests[args.start:args.end]
    
    print(f"Found {len(all_tests)} total tests")
    print(f"Will run tests {args.start} to {args.end} ({len(tests_to_run)} tests)")
    print(f"Model: {args.model}")
    
    # Confirm before starting
    response = input("\nProceed? (y/n): ")
    if response.lower() != 'y':
        print("Aborted")
        return
    
    # Run tests and collect results
    results = []
    start_time = datetime.now()
    
    for i, test_id in enumerate(tests_to_run, 1):
        print(f"\n[{i}/{len(tests_to_run)}] Processing {test_id}")
        
        result = run_test(test_id, args.model)
        results.append(result)
        
        # Print running summary
        passed = sum(1 for r in results if r["passed"])
        failed = sum(1 for r in results if not r["passed"])
        print(f"\nRunning total: {passed} passed, {failed} failed")
        
        if not args.continue_on_error and result["status"] == "error":
            print("\nStopping due to error (use --continue-on-error to continue)")
            break
    
    # Generate summary
    end_time = datetime.now()
    duration = end_time - start_time
    
    passed_tests = [r for r in results if r["passed"]]
    failed_tests = [r for r in results if not r["passed"]]
    
    summary = {
        "model": args.model,
        "category": args.category,
        "range": f"{args.start}-{args.end}",
        "total_tests": len(results),
        "passed": len(passed_tests),
        "failed": len(failed_tests),
        "pass_rate": len(passed_tests) / len(results) * 100 if results else 0,
        "duration_seconds": duration.total_seconds(),
        "timestamp": datetime.now().isoformat(),
        "results": results
    }
    
    # Save detailed results
    output_file = Path(f"outputs/batch_results/{args.category}_{args.model}_{args.start}-{args.end}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Model: {args.model}")
    print(f"Tests run: {len(results)}")
    print(f"Passed: {len(passed_tests)} ({summary['pass_rate']:.1f}%)")
    print(f"Failed: {len(failed_tests)}")
    print(f"Duration: {duration}")
    print(f"\nResults saved to: {output_file}")
    
    # List failed tests for easy reference
    if failed_tests:
        print(f"\nFailed tests ({len(failed_tests)}):")
        for test in failed_tests[:10]:  # Show first 10
            print(f"  - {test['test_id']}: {test['status']}")
        if len(failed_tests) > 10:
            print(f"  ... and {len(failed_tests) - 10} more")
    
    # Exit with appropriate code
    sys.exit(0 if len(failed_tests) == 0 else 1)


if __name__ == "__main__":
    main()