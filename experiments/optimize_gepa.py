"""Simple GEPA-based instruction optimization for BFCL tests.

Usage:
    python experiments/optimize_gepa.py --test-subset multi_turn_base --num-tests <HOW MANY TESTS> --gepa-scoring-mode
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Optional

import dspy
from dspy.evaluate import Evaluate
from dspy.teleprompt import GEPA

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.benchmarks.bfcl import loader as bfcl_loader
from tests.utils.fastagent_helpers import MessageSerializer


def _stringify_question(question: Any) -> str:
    """Normalize BFCL question payloads into text."""
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


class BFCLExample(dspy.Example):
    """BFCL test case as a DSPy example."""

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
    """Prediction wrapper carrying both scalar score and textual feedback."""

    def __init__(self, score: float, feedback: str) -> None:
        super().__init__(score=score, feedback=feedback)


class BFCLAgent(dspy.Module):
    """Run BFCL tests with mutable instructions managed by GEPA."""

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
        """Run a single BFCL test and return the score plus tool usage info."""
        self._instruction_path.parent.mkdir(parents=True, exist_ok=True)
        instruction_text = self._instruction_text()
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

    def _instruction_text(self) -> str:
        instructions = getattr(self.prompt_predictor.signature, "instructions", "")
        if isinstance(instructions, (list, tuple)):
            return "\n".join(str(part) for part in instructions if part)
        return str(instructions or "")

    def get_instruction_text(self) -> str:
        return self._instruction_text()

    @staticmethod
    def _collect_tool_names(output_dir: Path, test_id: str) -> list[str]:
        complete_file = output_dir / "raw" / f"{test_id}_complete.json"
        if not complete_file.exists():
            return []

        try:
            with open(complete_file, encoding="utf-8") as handle:
                complete_data = json.load(handle)
        except json.JSONDecodeError:
            return []

        tool_calls = MessageSerializer.extract_tool_calls_by_turn(complete_data)
        names: list[str] = []
        for turn in tool_calls:
            for call in turn:
                function = call.get("function")
                if function:
                    names.append(function)
        return names


def bfcl_metric_with_feedback(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Optional[Any] = None,
    pred_name: Optional[str] = None,
    pred_trace: Optional[Any] = None,
) -> dict[str, Any]:
    """Metric that provides feedback to GEPA about test failures."""
    
    score = 1.0 if pred.passed else 0.0
    
    # Build feedback based on what went wrong
    feedback_parts = []
    
    if not pred.passed:
        feedback_parts.append(f"Test {gold.test_id} FAILED")
        
        # Check if expected tools were used
        expected = set(gold.expected_tools)
        used = set(pred.tools_used)
        
        if expected and used:
            missing = expected - used
            extra = used - expected
            
            if missing:
                feedback_parts.append(f"Missing expected tools: {', '.join(missing)}")
            if extra:
                feedback_parts.append(f"Used unexpected tools: {', '.join(extra)}")
        elif expected and not used:
            feedback_parts.append(f"No tools were called, but expected: {', '.join(expected)}")
        
        # Add snippet of error output if available
        if pred.output:
            error_lines = [line for line in pred.output.split('\n') if 'error' in line.lower() or 'failed' in line.lower()]
            if error_lines:
                feedback_parts.append(f"Error output: {error_lines[0][:200]}")
    else:
        feedback_parts.append(f"Test {gold.test_id} PASSED")
    
    feedback = " | ".join(feedback_parts)
    
    return MetricFeedback(score=score, feedback=feedback)


def load_test_cases(subset: str, limit: int) -> list[BFCLExample]:
    """Load BFCL entries using the shared loader utilities."""

    test_ids = bfcl_loader.find_tests_in_category(subset, limit=limit)
    examples: list[BFCLExample] = []

    for test_id in test_ids[:limit]:
        try:
            entry = bfcl_loader.load_test_entry(test_id)
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"Warning: unable to load {test_id}: {exc}")
            continue

        question = _stringify_question(entry.get("question", ""))
        expected_tools = entry.get("involved_classes", []) or []
        example = BFCLExample(test_id=test_id, question=question, expected_tools=expected_tools)
        examples.append(example.with_inputs("test_id", "question"))

    return examples[:limit]


def run_baseline(agent: BFCLAgent, examples: list[BFCLExample]) -> float:
    """Run baseline evaluation."""
    print(f"Running baseline with {len(examples)} tests...")
    
    passed = 0
    for example in examples:
        pred = agent(test_id=example.test_id, question=example.question)
        if pred.passed:
            passed += 1
    
    score = passed / len(examples) if examples else 0.0
    print(f"Baseline pass rate: {score:.2%} ({passed}/{len(examples)})")
    return score


def main():
    parser = argparse.ArgumentParser(description="Optimize BFCL instructions using GEPA")
    parser.add_argument("--test-subset", default="multi_turn_base", 
                       help="Test category to use (e.g., multi_turn_base)")
    parser.add_argument("--num-tests", type=int, default=10,
                       help="Number of tests to use for optimization")
    parser.add_argument("--model", default="gpt-5",
                       help="Model to use for test evaluation")
    parser.add_argument("--reflection-model", default="gpt-5",
                       help="Model to use for GEPA reflection")
    parser.add_argument("--max-evaluations", type=int, default=20,
                       help="Maximum number of GEPA metric calls")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/gepa"),
                       help="Output directory")
    parser.add_argument("--auto", choices=['light', 'medium', 'heavy'], default='light',
                       help="GEPA auto-tuning mode")
    parser.add_argument("--instruction-file", type=Path, default=Path("tests/benchmarks/bfcl/instruction.txt"),
                       help="Path to the seed BFCL instruction file")
    parser.add_argument("--pytest-binary", default="pytest",
                       help="Pytest binary to invoke (default: pytest on PATH)")
    parser.add_argument("--gepa-scoring-mode", action="store_true",
                       help="Enable BFCL scoring-only logging during runs")
    
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("GEPA Instruction Optimization for BFCL")
    print("=" * 60)
    
    # Load test cases
    examples = load_test_cases(args.test_subset, args.num_tests)
    if not examples:
        print(f"Error: No tests found for subset '{args.test_subset}'")
        return
    
    print(f"\nLoaded {len(examples)} test cases from {args.test_subset}")
    
    # Load original instructions
    instruction_file = args.instruction_file
    if not instruction_file.exists():
        print(f"Error: Instruction file not found: {instruction_file}")
        return
    
    original_instructions = instruction_file.read_text()
    print(f"Original instructions: {len(original_instructions)} chars")
    
    # Create agent with original instructions
    agent = BFCLAgent(
        instruction_text=original_instructions,
        model=args.model,
        base_dir=args.output_dir,
        pytest_binary=args.pytest_binary,
        enable_scoring_mode=args.gepa_scoring_mode,
    )
    
    # Run baseline
    baseline_score = run_baseline(agent, examples)
    
    # Setup DSPy with reflection LM
    reflection_lm = dspy.LM(args.reflection_model)
    dspy.configure(lm=reflection_lm)
    
    print("\n" + "=" * 60)
    print("Starting GEPA optimization...")
    print("=" * 60)
    print(f"Max evaluations: {args.max_evaluations}")
    print(f"Auto-tuning mode: {args.auto}")
    print(f"Reflection model: {args.reflection_model}")
    
    # Create GEPA optimizer
    gepa = GEPA(
        metric=bfcl_metric_with_feedback,
        auto=args.auto,
        reflection_lm=reflection_lm,
        reflection_minibatch_size=3,
        log_dir=str(args.output_dir / "gepa_logs"),
        track_stats=True,
        seed=42
    )
    
    # Split into train/dev
    train_size = int(len(examples) * 0.7)
    trainset = examples[:train_size]
    devset = examples[train_size:]
    
    print(f"Train set: {len(trainset)} tests")
    print(f"Dev set: {len(devset)} tests")
    
    # Optimize
    optimized_agent = gepa.compile(agent, trainset=trainset, valset=devset)
    
    # Evaluate optimized version
    print("\n" + "=" * 60)
    print("Evaluating optimized instructions...")
    print("=" * 60)
    
    evaluate = Evaluate(
        devset=devset,
        metric=bfcl_metric_with_feedback,
        display_progress=True,
        display_table=False
    )
    
    final_result = evaluate(optimized_agent)
    final_score = float(final_result.score)
    
    optimized_instruction_path = args.output_dir / "optimized_instructions.txt"
    optimized_instruction_path.write_text(optimized_agent.get_instruction_text(), encoding="utf-8")

    metadata = {
        "baseline_score": baseline_score,
        "final_score": final_score,
        "test_subset": args.test_subset,
        "num_tests": len(examples),
        "train_size": len(trainset),
        "dev_size": len(devset),
        "model": args.model,
        "reflection_model": args.reflection_model,
        "max_evaluations": args.max_evaluations,
        "test_ids": [ex.test_id for ex in examples],
        "optimized_instruction_path": str(optimized_instruction_path),
    }
    
    metadata_file = args.output_dir / "optimization_metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))
    
    print("\n" + "=" * 60)
    print("Optimization Complete!")
    print("=" * 60)
    print(f"Baseline score: {baseline_score:.2%}")
    print(f"Final score: {final_score:.2%}")
    print(f"Improvement: {(final_score - baseline_score):.2%}")
    print(f"\nMetadata saved to: {metadata_file}")
    print(f"GEPA logs saved to: {args.output_dir / 'gepa_logs'}")
    print("\nCheck the GEPA logs for optimized prompts and detailed traces.")


if __name__ == "__main__":
    main()
