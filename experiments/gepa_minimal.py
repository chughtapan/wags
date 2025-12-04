#!/usr/bin/env python
"""GEPA experiment using BFCL scoring."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
INSTR = ROOT / "tests/benchmarks/bfcl/instruction.txt"

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import dspy
from dspy.teleprompt.gepa.gepa import GEPA
from tests.benchmarks.bfcl.test_bfcl import _run_bfcl_test, _validate_from_complete_json

TEST_IDS = ["multi_turn_base_121", "multi_turn_base_167"]
MODEL = "gpt-5"
TEMP = 0.0

# ---------------------------------------------------------------------------
# Safe async wrapper (prevents GEPA worker event-loop explosions)
# ---------------------------------------------------------------------------
def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # normal case when called from main thread

    # If already inside a running event loop (GEPA worker): create a private loop
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ---------------------------------------------------------------------------
# BFCL score
# ---------------------------------------------------------------------------
async def _run_single(test_id):
    out = ROOT / "experiments/min" / test_id
    out.mkdir(parents=True, exist_ok=True)
    json_path = await _run_bfcl_test(test_id, MODEL, TEMP, out)
    return _validate_from_complete_json(test_id, json_path)["validation"]["valid"]

def bfcl_score(text: str):
    INSTR.write_text(text)
    async def run_all():
        results = [await _run_single(t) for t in TEST_IDS]
        return sum(results) / len(results)
    return run_async(run_all())

# ---------------------------------------------------------------------------
# GEPA metric + minimal DSPy module
# ---------------------------------------------------------------------------
def metric(gold, pred, *_):
    return bfcl_score(pred.instruction)

class Program(dspy.Module):
    def __init__(self, text):
        super().__init__()
        self.text = text
    def forward(self, x=None):
        return dspy.Prediction(instruction=self.text)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    base = INSTR.read_text()
    dspy.configure(lm=dspy.LM(MODEL))

    # GEPA requires at least one input field
    train = [dspy.Example(x="dummy").with_inputs("x")]

    gepa = GEPA(metric=metric, auto="light", reflection_lm=dspy.LM(MODEL))
    tuned = gepa.compile(student=Program(base), trainset=train, valset=train)

    print("\n=== Optimized Instruction ===\n")
    print(tuned.instruction)