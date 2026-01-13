"""
agent.py

DSPy module wrapper for running BFCL tests with pytest
"""

from __future__ import annotations
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, List
import dspy
from tests.benchmarks.bfcl import evaluator as bfcl_evaluator
from tests.utils.fastagent_helpers import MessageSerializer
from .logging_utils import sha256_text, RUN_CTX, append_jsonl, utc_now_iso, safe_json



class BFCLExample(dspy.Example):
    """
    DSPy Example wrapper for BFCL cases/examples
    """
    
    def __init__(
        self,
        test_id: str | None = None,
        question: str | None = None,
        *,
        base: dspy.Example | None = None,
        **kwargs: Any
    ):
        if base is None:
            super().__init__(test_id=test_id, question=question, **kwargs)
        else:
            super().__init__(base=base, **kwargs)
        

class BFCLAgent(dspy.Module):
    """
    DSPy module that evaluates a given instruction prompt by running
    BFCL tests (with pytest) and parsing resulting outputs
    """
    
    def __init__(
        self, 
        instruction_text: str,
        model: str,
        execution_lm: dspy.LM,
        base_dir: Path,
        pytest_binary: str,
        enable_scoring_mode: bool
    ):
        super().__init__()
        self.model = model
        self.execution_lm = execution_lm
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.pytest_binary = pytest_binary
        self.enable_scoring_mode = enable_scoring_mode
        
        # The file at this path is changed before each run
        self._instruction_path = self.base_dir / "current_instruction.txt"
        
        # Define the model's task
        signature = dspy.Signature(
            "prompt_input -> prompt_output",
            instructions=instruction_text
        )
        
        # dspy.Predict handles logic of constructing prompt 
        # and sending it to the LM
        self.prompt_predictor = dspy.Predict(signature)
    

    def forward(self, test_id: str, question: str) -> dspy.Prediction:
        """
        Run a single BFCL test case using the current instruction prompt
        """
        phase = "unknown"
        if RUN_CTX is not None:
            if test_id in RUN_CTX.train_ids:
                phase = "gepa_train"
            elif test_id in RUN_CTX.dev_ids:
                phase = "gepa_dev"
            else:
                phase = "baseline"
                
        test_number = None
        try:
            test_number = int(test_id.rsplit("_", 1)[-1])
        except Exception:
            pass


        # Initialize timing
        t0 = time.perf_counter()
        timing: dict[str, float] = {}

        # dspy trace anchor
        try:
            t_trace = time.perf_counter()
            with dspy.context(lm=self.execution_lm):
                _ = self.prompt_predictor(prompt_input=question)
            timing["dspy_trace_anchor_s"] = time.perf_counter() - t_trace
        except Exception as e:
            timing["dspy_trace_anchor_s"] = 0.0
            print(f"[TRACE_ANCHOR_ERROR] {type(e).__name__}: {e}")
        
        # Write current instruction
        instruction_text = self.get_instruction_text()
        instruction_hash = sha256_text(instruction_text)
        
        t_write = time.perf_counter()
        self._instruction_path.write_text(instruction_text, encoding="utf-8")
        timing["write_instruction_s"] = time.perf_counter() - t_write

        # Create a unique directory for each individual run
        run_uid = uuid.uuid4().hex[:12]
        run_dir = self.base_dir / "runs" / f"{test_id}__{run_uid}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Construct the pytest command
        cmd = [
            self.pytest_binary,
            f"tests/benchmarks/bfcl/test_bfcl.py::test_bfcl[{test_id}]",
            "--model", 
            self.model, 
            "--instruction-file", 
            str(self._instruction_path),
            "--output-dir",
            str(run_dir),
            "-q",
            "-x"
        ]
        if self.enable_scoring_mode:
            cmd.append("--gepa-scoring-mode")

        # Run the pytest command
        t_pytest = time.perf_counter()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        timing["pytest_run_s"] = time.perf_counter() - t_pytest
        
        # Parse outputs and evaluate
        complete_path = run_dir / "raw" / f"{test_id}_complete.json"

        tool_calls_by_turn: List[List[dict[str, Any]]] = []
        executable_responses: List[List[str]] = []
        evaluation: dict[str, Any] | None = None
        eval_error: str | None = None

        t_eval = time.perf_counter()
        if complete_path.exists():
            try:
                complete_data = json.loads(complete_path.read_text())
                tool_calls_by_turn = MessageSerializer.extract_tool_calls_by_turn(complete_data)
                
                t_fmt = time.perf_counter()
                executable_responses = MessageSerializer.format_to_executable(tool_calls_by_turn)
                timing["format_to_executable_s"] = time.perf_counter() - t_fmt
                
                t_chk = time.perf_counter()
                evaluation = bfcl_evaluator._run_evaluation(
                    test_id,
                    tool_calls_by_turn,
                    executable_responses,
                )
                timing["bfcl_checker_s"] = time.perf_counter() - t_chk
            except Exception as e:
                eval_error = f"{type(e).__name__}: {e}"
        
        else:
            eval_error = "Complete JSON not found (agent may have crashed)"
            
        timing["parse_and_eval_s"] = time.perf_counter() - t_eval
        
        tools_used = [call.get("function") for turn in tool_calls_by_turn for call in turn if call.get("function")]
        behavior_summary = self._summarize_behavior_from_calls(tool_calls_by_turn)

        timing["total_forward_s"] = time.perf_counter() - t0
        
        if RUN_CTX is not None:
            record = {
                "ts": utc_now_iso(),
                "run_id": RUN_CTX.run_id,

                "phase": phase,
                "test_id": test_id,
                "test_number": test_number,

                "instruction": {
                    "hash": instruction_hash,
                },

                "evaluation": {
                    "valid": bool(
                        evaluation.get("validation", {}).get("valid", False)
                    ) if evaluation else False,
                    "eval_error": eval_error,
                },

                "run_dir": str(run_dir),
            }

            append_jsonl(
                RUN_CTX.run_index_path,
                safe_json(record)
            )


        # Final prediction for the current case
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
            run_dir=str(run_dir),
            timing=timing
        )
    
    def get_instruction_text(self) -> str:
        """
        Return the current instruction text used by dspy
        """
        instructions = getattr(self.prompt_predictor.signature, "instructions", "")
        if isinstance(instructions, (list, tuple)):
            return "\n".join(str(p) for p in instructions if p)
        return str(instructions or "")
    
    @staticmethod
    def _summarize_behavior_from_calls(tool_calls: List[List[dict[str, Any]]]) -> str:
        """
        Summarize tool-use behavior for logging and feedback
        """
        tool_seq: List[str] = []
        for turn in tool_calls:
            for call in turn:
                fn = call.get("function")
                if fn:
                    tool_seq.append(fn)
                    
        return (
            f"TOOLS: {' -> '.join(tool_seq) or 'NONE'}\n"
            f"NUM_TOOLS: {len(tool_seq)}"
        )
        