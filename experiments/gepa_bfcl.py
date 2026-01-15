# NOTE:
# This script performs instruction-only optimization using GEPA over BFCL tests.
# The BFCL agent is invoked via pytest.

"""
GEPA-based instruction optimization for BFCL tests with first-class logging/artifacts.
Run via: `python experiments/gepa_bfcl.py --instruction-file path/to/instruction.txt [other options]`
"""

import argparse
import json
import subprocess
import hashlib
import uuid
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import dspy
from dspy.teleprompt import GEPA

# Ensure repo root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.benchmarks.bfcl import loader as bfcl_loader
from tests.benchmarks.bfcl import evaluator as bfcl_evaluator
from tests.utils.fastagent_helpers import MessageSerializer


# -------------------------
# JSON / logging utilities
# -------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_json(obj: Any) -> Any:
    """Best-effort JSON-serializable conversion."""
    try:
        json.dumps(obj)
        return obj
    except Exception:
        if isinstance(obj, dict):
            return {str(k): safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [safe_json(x) for x in obj]
        if hasattr(obj, "__dict__"):
            return safe_json(obj.__dict__)
        return repr(obj)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class TeeIO:
    """Mirror writes to both the real stream and a file."""
    def __init__(self, real_stream, log_file):
        self.real_stream = real_stream
        self.log_file = log_file

    def write(self, s):
        self.real_stream.write(s)
        self.log_file.write(s)

    def flush(self):
        self.real_stream.flush()
        self.log_file.flush()

    def isatty(self):
        return False


@dataclass
class RunContext:
    run_id: str
    output_dir: Path
    metric_calls_path: Path
    candidate_snapshots_path: Path
    train_ids: set[str]
    dev_ids: set[str]
    score_definition: dict[str, Any]


RUN_CTX: RunContext | None = None


# -------------------------
# BFCL formatting helpers
# -------------------------

def _stringify_question(question: Any) -> str:
    """Best-effort stringify for trace anchoring. BFCL is multi-turn; this picks the first user content."""
    if isinstance(question, list) and question:
        first = question[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("content", ""))
        if isinstance(first, list) and first:
            # BFCL questions often look like [[{role, content}], [{...}], ...]
            msg0 = first[0]
            if isinstance(msg0, dict):
                return str(msg0.get("content", ""))
    if isinstance(question, dict):
        return str(question.get("content", ""))
    if isinstance(question, str):
        return question
    return ""


def _fn_name(executable_call: str) -> str:
    if not executable_call:
        return ""
    idx = executable_call.find("(")
    return executable_call[:idx] if idx != -1 else executable_call


def _soft_turn_score(gt_turn: list[str], pred_turn: list[str]) -> float:
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
    def __init__(self, test_id: str | None = None, question: str | None = None, *, base: dspy.Example | None = None, **kwargs: Any):
        if base is not None:
            super().__init__(base=base, **kwargs)
        else:
            super().__init__(test_id=test_id, question=question, **kwargs)


class MetricFeedback(dspy.Prediction):
    def __init__(self, score: float, feedback: str) -> None:
        super().__init__(score=score, feedback=feedback)


class BFCLAgent(dspy.Module):
    """DSPy module wrapper around pytest-driven BFCL evaluation."""

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

    def forward(self, test_id: str, question: str) -> dspy.Prediction:
        # ----- timing breakdown -----
        t0 = time.perf_counter()
        timing: dict[str, float] = {}

        # ---- Trace anchor: invoke predictor so GEPA has a component trace ----
        try:
            t_a = time.perf_counter()
            _ = self.prompt_predictor(prompt_input=question)
            timing["dspy_trace_anchor_s"] = time.perf_counter() - t_a
        except Exception:
            timing["dspy_trace_anchor_s"] = 0.0

        # Write current instruction
        t_w = time.perf_counter()
        instruction_text = self.get_instruction_text()
        instruction_hash = sha256_text(instruction_text)
        self._instruction_path.write_text(instruction_text, encoding="utf-8")
        timing["write_instruction_s"] = time.perf_counter() - t_w

        # Unique run dir prevents stale artifacts reuse
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

        # Run pytest
        t_p = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, text=True)
        timing["pytest_run_s"] = time.perf_counter() - t_p

        complete_path = output_dir / "raw" / f"{test_id}_complete.json"

        tool_calls_by_turn: list[list[dict[str, Any]]] = []
        executable_responses: list[list[str]] = []
        evaluation: dict[str, Any] | None = None
        eval_error: str | None = None

        # Parse + evaluate
        t_e = time.perf_counter()
        if complete_path.exists():
            try:
                complete_data = json.loads(complete_path.read_text())
                tool_calls_by_turn = MessageSerializer.extract_tool_calls_by_turn(complete_data)

                t_fmt = time.perf_counter()
                executable_responses = MessageSerializer.format_to_executable(tool_calls_by_turn)
                timing["format_to_executable_s"] = time.perf_counter() - t_fmt

                t_chk = time.perf_counter()
                evaluation = bfcl_evaluator._run_evaluation(test_id, tool_calls_by_turn, executable_responses)
                timing["bfcl_checker_s"] = time.perf_counter() - t_chk
            except Exception as e:
                eval_error = f"{type(e).__name__}: {e}"
        else:
            eval_error = "Complete JSON not found (agent may have crashed before serialization)."
        timing["parse_and_eval_s"] = time.perf_counter() - t_e

        tools_used = [call.get("function") for turn in tool_calls_by_turn for call in turn if call.get("function")]
        behavior_summary = self._summarize_behavior_from_calls(tool_calls_by_turn)

        timing["total_forward_s"] = time.perf_counter() - t0

        return dspy.Prediction(
            test_id=test_id,
            instruction_hash=instruction_hash,
            instruction_text=instruction_text,
            tools_used=tools_used,
            behavior=behavior_summary,
            executable_responses=executable_responses,
            evaluation=evaluation,
            eval_error=eval_error,
            pytest_stdout=result.stdout,
            pytest_stderr=result.stderr,
            run_dir=str(output_dir),
            timing=timing,
        )


# -------------------------
# Metric (logs every call incrementally)
# -------------------------

def bfcl_metric_with_feedback(
    gold: dspy.Example,
    pred: dspy.Prediction,
    trace: Optional[Any] = None,
    pred_name: Optional[str] = None,
    pred_trace: Optional[Any] = None,
) -> MetricFeedback:
    """
    Score definition (explicitly persisted in run_manifest.json):
      hard_valid ∈ {0,1} = BFCL checker validation.valid
      soft ∈ [0,1] = turn-wise overlap score based on function-name overlap (F1-like)
      final = 0.9*hard_valid + 0.1*soft
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

    hard_valid = False
    if evaluation and isinstance(evaluation, dict):
        hard_valid = bool(evaluation.get("validation", {}).get("valid", False))

    soft = _soft_sequence_score(gt, pred_exec) if gt else (1.0 if hard_valid else 0.0)
    final_score = (1.0 if hard_valid else 0.0) * 0.9 + soft * 0.1

    split = None
    if RUN_CTX and test_id:
        if test_id in RUN_CTX.train_ids:
            split = "train"
        elif test_id in RUN_CTX.dev_ids:
            split = "dev"
        else:
            split = "unknown"

    feedback_parts.append(f"RESULT: {'PASS' if hard_valid else 'FAIL'}")
    feedback_parts.append(f"SCORE_BREAKDOWN: hard={'1.0' if hard_valid else '0.0'} soft={soft:.3f} final={final_score:.3f}")
    if split:
        feedback_parts.append(f"SPLIT: {split}")

    if involved_classes:
        feedback_parts.append(f"INVOLVED_CLASSES (servers mounted): {', '.join(involved_classes)}")
    if excluded:
        feedback_parts.append(f"EXCLUDED_FUNCTIONS: {', '.join(excluded)}")

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
        feedback_parts.append(_diff_summary(gt, pred_exec))

    if excluded and pred_exec:
        used_fns = {_fn_name(s) for turn in pred_exec for s in turn}
        bad = sorted(set(excluded) & used_fns)
        if bad:
            feedback_parts.append(f"CONSTRAINT_VIOLATION: used excluded function(s): {', '.join(bad)}")

    if hasattr(pred, "behavior"):
        feedback_parts.append("BEHAVIOR_SUMMARY:")
        feedback_parts.append(str(pred.behavior))

    run_dir = getattr(pred, "run_dir", None)
    if run_dir:
        feedback_parts.append(f"RUN_DIR: {run_dir}")

    # ---- First-class machine-readable metric call record ----
    if RUN_CTX and test_id:
        record = {
            "ts": utc_now_iso(),
            "run_id": RUN_CTX.run_id,
            "test_id": test_id,
            "split": split,
            "instruction_hash": getattr(pred, "instruction_hash", None),
            "hard_valid": hard_valid,
            "soft": soft,
            "final": final_score,
            "timing": getattr(pred, "timing", None),
            "run_dir": run_dir,
            "eval_error": eval_error,
            "evaluator_validation": safe_json(evaluation.get("validation")) if isinstance(evaluation, dict) else None,
            "evaluator_irrelevance": safe_json(evaluation.get("irrelevance_check")) if isinstance(evaluation, dict) else None,
        }
        append_jsonl(RUN_CTX.metric_calls_path, record)

        # Opportunistic candidate snapshot (what GEPA is “trying”)
        snap = {
            "ts": utc_now_iso(),
            "run_id": RUN_CTX.run_id,
            "instruction_hash": getattr(pred, "instruction_hash", None),
            "instruction_text": getattr(pred, "instruction_text", None),
            "latest_eval": {
                "test_id": test_id,
                "split": split,
                "hard_valid": hard_valid,
                "soft": soft,
                "final": final_score,
            },
        }
        append_jsonl(RUN_CTX.candidate_snapshots_path, snap)

    return MetricFeedback(score=final_score, feedback="\n".join(feedback_parts))


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
# Run manifest + environment capture
# -------------------------

def try_git_info() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        info["git_commit"] = head.stdout.strip() if head.returncode == 0 else None
        st = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
        info["git_dirty"] = bool(st.stdout.strip())
    except Exception:
        info["git_commit"] = None
        info["git_dirty"] = None
    return info


def build_score_definition() -> dict[str, Any]:
    return {
        "hard_valid": "BFCL evaluator validation.valid (boolean) from multi_turn_checker",
        "soft": "turn-wise function-name overlap F1-like score (ignores args), averaged across turns",
        "final": "0.9*hard_valid + 0.1*soft",
        "note": "Optimization and candidate scores use `final`. Hard-valid-rate is also reported separately for clarity.",
    }


# -------------------------
# Main
# -------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-subset", default="multi_turn_base")
    parser.add_argument("--num-tests", type=int, default=10)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--reflection-model", default="gpt-5-mini")
    parser.add_argument("--max-evaluations", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/gepa_on_bfcl"))
    parser.add_argument("--auto", choices=["light", "medium", "heavy"], default=None)
    parser.add_argument("--instruction-file", type=Path, required=True)
    parser.add_argument("--pytest-binary", default="pytest")
    parser.add_argument("--gepa-scoring-mode", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Mirror stdout/stderr to console.log automatically ----
    console_log_path = args.output_dir / "console.log"
    console_log_f = console_log_path.open("w", encoding="utf-8")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = TeeIO(real_out, console_log_f)
    sys.stderr = TeeIO(real_err, console_log_f)

    overall_t0 = time.perf_counter()
    timings: dict[str, float] = {}

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    metric_calls_path = args.output_dir / "metric_calls.jsonl"
    candidate_snapshots_path = args.output_dir / "candidate_snapshots.jsonl"

    score_def = build_score_definition()

    try:
        print(f"[{utc_now_iso()}] RUN_ID={run_id}")
        print(f"[{utc_now_iso()}] output_dir={args.output_dir}")

        # Load dataset and split
        t_load = time.perf_counter()
        examples = load_test_cases(args.test_subset, args.num_tests)
        train_size = int(0.7 * len(examples))
        trainset, devset = examples[:train_size], examples[train_size:]
        timings["load_dataset_s"] = time.perf_counter() - t_load

        train_ids = {e.test_id for e in trainset}
        dev_ids = {e.test_id for e in devset}

        (args.output_dir / "dataset_split.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "test_subset": args.test_subset,
                    "num_tests": args.num_tests,
                    "train_ids": sorted(train_ids),
                    "dev_ids": sorted(dev_ids),
                    "train_size": len(train_ids),
                    "dev_size": len(dev_ids),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # Initialize global run context for metric logging
        global RUN_CTX
        RUN_CTX = RunContext(
            run_id=run_id,
            output_dir=args.output_dir,
            metric_calls_path=metric_calls_path,
            candidate_snapshots_path=candidate_snapshots_path,
            train_ids=train_ids,
            dev_ids=dev_ids,
            score_definition=score_def,
        )

        instruction_text = args.instruction_file.read_text(encoding="utf-8")
        instruction_hash = sha256_text(instruction_text)

        # Manifest: config, hyperparams, environment, git, score definition, dataset split
        manifest = {
            "run_id": run_id,
            "created_at": utc_now_iso(),
            "argv": sys.argv,
            "args": safe_json(vars(args)),
            "instruction_file": str(args.instruction_file),
            "instruction_hash": instruction_hash,
            "score_definition": score_def,
            "models": {
                "agent_model": args.model,
                "reflection_model": args.reflection_model,
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
        (args.output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        agent = BFCLAgent(
            instruction_text=instruction_text,
            model=args.model,
            execution_lm=execution_lm,
            base_dir=args.output_dir,
            pytest_binary=args.pytest_binary,
            enable_scoring_mode=args.gepa_scoring_mode,
        )

        # Baseline
        t_base = time.perf_counter()
        baseline_valid = 0
        baseline_total = len(examples)
        baseline_details: list[dict[str, Any]] = []
        for e in examples:
            pred = agent(test_id=e.test_id, question=e.question)
            valid = False
            if getattr(pred, "evaluation", None):
                valid = bool(pred.evaluation.get("validation", {}).get("valid", False))
            baseline_valid += 1 if valid else 0
            baseline_details.append(
                {
                    "test_id": e.test_id,
                    "valid": valid,
                    "instruction_hash": getattr(pred, "instruction_hash", None),
                    "run_dir": getattr(pred, "run_dir", None),
                    "timing": getattr(pred, "timing", None),
                    "eval_error": getattr(pred, "eval_error", None),
                }
            )
        timings["baseline_s"] = time.perf_counter() - t_base

        baseline_valid_rate = baseline_valid / max(baseline_total, 1)
        (args.output_dir / "baseline.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "instruction_hash": instruction_hash,
                    "bfcl_valid_rate": baseline_valid_rate,
                    "valid": baseline_valid,
                    "total": baseline_total,
                    "test_ids": [e.test_id for e in examples],
                    "model": args.model,
                    "score_definition": score_def,
                    "runs": baseline_details,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[{utc_now_iso()}] Baseline BFCL valid rate: {baseline_valid_rate:.3f} ({baseline_valid}/{baseline_total})")

        # GEPA
        t_gepa = time.perf_counter()
        reflection_lm = dspy.LM(args.reflection_model)
        execution_lm = dspy.LM(args.model)
        
        dspy.configure(lm=reflection_lm)

        gepa_kwargs: dict[str, Any] = dict(
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
            
        gepa_kwargs["reflection_lm"] = args.reflection_model

        # Persist GEPA config/hparams exactly
        (args.output_dir / "gepa_config.json").write_text(json.dumps(safe_json(gepa_kwargs), indent=2), encoding="utf-8")

        gepa = GEPA(**gepa_kwargs)
        optimized_agent = gepa.compile(agent, trainset=trainset, valset=devset)
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
            "score_definition": score_def,
            "dataset_split": {
                "train_ids": sorted(train_ids),
                "dev_ids": sorted(dev_ids),
            },
            "baseline": {
                "bfcl_valid_rate_over_all_examples": baseline_valid_rate,
                "examples_used": [e.test_id for e in examples],
                "valid_count": baseline_valid,
                "total_count": baseline_total,
            },
            "gepa": {
                "objective": "final (0.9*hard_valid + 0.1*soft) aggregated over dev set by GEPA internals",
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
        # Restore streams and close file
        sys.stdout.flush()
        sys.stderr.flush()
        sys.stdout = real_out
        sys.stderr = real_err
        console_log_f.close()


if __name__ == "__main__":
    main()
