"""
Minimal GEPA use case
"""

import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import dspy
from dspy.teleprompt import GEPA
from dspy.evaluate import Evaluate



# 1. Define a tiny task

class QAExample(dspy.Example):
    """Simple question–answer example."""
    def __init__(self, question: str | None = None, answer: str | None = None, *, base: dspy.Example | None = None,**kwargs,):
        if base is not None:
            super().__init__(base=base, **kwargs)
        else:
            super().__init__(question=question, answer=answer, **kwargs)

    def __repr__(self):
        return f"Q: {self.question} | A: {self.answer}"


examples = [
    QAExample(
        "What is 2 + 2? If the result is greater than 3, subtract 2.",
        "2"
    ).with_inputs("question"),
    QAExample(
        "What is the capital of France? Return the number of letters in the answer.",
        "5"
    ).with_inputs("question"),
    QAExample(
        "What color is the sky? Assume no atmosphere.",
        "black"
    ).with_inputs("question"),
    QAExample(
        "What is 10 minus 3? If the result is odd, subtract 1.",
        "6"
    ).with_inputs("question"),
    QAExample(
        "What is the largest planet in our solar system? Answer in one word only. Explain your reasoning.",
        "jupiter"
    ).with_inputs("question"),
    QAExample(
        "Who wrote 'To Kill a Mockingbird'? Return only the last name.",
        "lee"
    ).with_inputs("question"),
    QAExample(
        "What is the boiling point of water in Celsius? If conditions differ from standard, return 'unknown'.",
        "unknown"
    ).with_inputs("question"),
    QAExample(
        "What is the square root of 16? Return the result minus 1.",
        "3"
    ).with_inputs("question"),
    QAExample(
        "What is the chemical symbol for gold? Return the symbol reversed.",
        "ua"
    ).with_inputs("question"),
    QAExample(
        "What is the dot product of [1,2] and [3,4]? If the result is greater than 10, subtract 1.",
        "10"
    ).with_inputs("question"),
    QAExample(
        "Where is the Taj Mahal located? Return only the country name.",
        "india"
    ).with_inputs("question"),
    QAExample(
        "What is the powerhouse of a cell? Answer the organelle name in reverse order",
        "airdnohcotim"
    ).with_inputs("question"),
    QAExample(
        "What is the RGB value of the color red? Return only the blue component.",
        "0"
    ).with_inputs("question"),
]



# 2. Define a DSPy module

class SimpleQAModel(dspy.Module):
    def __init__(self, instructions: str):
        super().__init__()
        self.predict = dspy.Predict(
            dspy.Signature("question -> answer", instructions=instructions)
        )

    def forward(self, question: str):
        return self.predict(question=question)

    # Required for GEPA instruction optimization
    def get_instruction_text(self) -> str:
        return self.predict.signature.instructions or ""



# 3. Metric

def exact_match_metric(
    gold,
    pred,
    trace=None,
    pred_name=None,
    pred_trace=None,
):
    score = (
        1.0
        if gold.answer.strip().lower() == pred.answer.strip().lower()
        else 0.0
    )
    return score




# 4. Main

def main():
    output_dir = Path("outputs/gepa_minimal")
    output_dir.mkdir(parents=True, exist_ok=True)

    lm = dspy.LM("openai/gpt-5")
    dspy.configure(lm=lm)

    # Initial weaker instruction
    seed_instruction = "Answer given question."

    model = SimpleQAModel(seed_instruction)

    # Baseline evaluation
    evaluator = Evaluate(
        devset=examples,
        metric=exact_match_metric,
        display_progress=True,
        num_threads=1,  
    )

    print("\n=== BASELINE ===")
    baseline = evaluator(model)
    (output_dir / "baseline.txt").write_text(f"Baseline score: {baseline.score}")

    # 5. Run GEPA
    gepa = GEPA(
        metric=exact_match_metric,
        max_full_evals=20,
        reflection_lm=lm,
        track_stats=True,
        seed=42,
    )

    train_size = int(0.7 * len(examples))
    trainset, devset = examples[:train_size], examples[train_size:]

    print("\n=== RUNNING GEPA ===")
    optimized_model = gepa.compile(
        model,
        trainset=trainset,
        valset=devset,
    )

    print("\n=== OPTIMIZED ===")
    final_score = evaluator(optimized_model)
    (output_dir / "optimized.txt").write_text(f"Optimized accuracy: {final_score.score}")

    # Correct way to access results (from real DSPy usage)
    results = optimized_model.detailed_results

    # Save candidates with proper instruction extraction
    print("\n=== CANDIDATES SAVED ===")
    candidates = []
    for i, cand in enumerate(results.candidates):
        instr = cand.get_instruction_text()  # This works!
        candidates.append({
            "candidate_id": i,
            "instruction_text": instr,
            "val_score": results.val_aggregate_scores[i],
        })
    (output_dir / "candidates.json").write_text(json.dumps(candidates, indent=2))

    # Save instruction evolution
    print("\n=== INSTRUCTIONS SAVED ===")
    instructions_text = (
        f"Original:\n{seed_instruction}\n\n"
        f"Optimized:\n{optimized_model.get_instruction_text()}"
    )
    (output_dir / "instructions.txt").write_text(instructions_text)

    # Metadata
    print("\n=== METADATA SAVED ===")
    meta = {
        "baseline_score": float(baseline.score),
        "final_score": float(final_score),
        "total_metric_calls": results.total_metric_calls,
        "num_full_val_evals": results.num_full_val_evals,
        "seed": results.seed,
    }
    (output_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

    print(f"\nAll outputs saved to {output_dir}/")


if __name__ == "__main__":
    main()