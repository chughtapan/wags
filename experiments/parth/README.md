# Parth's Experiment Work

Experiments run using the WAGS framework during Spring 2026.

## Directory structure

```
experiments/parth/
├── gepa/                      # GEPA prompt optimization on BFCL
│   ├── run.py                 # Orchestrator: runs GEPA optimization loop
│   ├── agent.py               # BFCLAgent wrapper for DSPy
│   ├── metrics.py             # BFCL metric with feedback for GEPA scoring
│   ├── scoring_utils.py       # Score parsing and aggregation helpers
│   ├── data_utils.py          # BFCL test case loading and filtering
│   ├── env_utils.py           # Model/env validation
│   ├── logging_utils.py       # JSONL logging, TeeIO, git info capture
│   ├── gepa_minimal.py        # Minimal standalone GEPA example
│   └── gepa_overview.txt      # Design notes on the optimization loop
│
└── feedback_ablation/         # Runtime feedback ablation study
    ├── run_experiment.py      # Runs one (subset x condition) cell via pytest
    ├── analyze_results.py     # Builds results dataframe + summary tables
    ├── cases.yaml             # Per-case trigger configs and feedback messages
    ├── baseline_stability.yaml # Baseline pass/fail/flaky labels per case
    └── configs/               # 28 JSON config files (A-G x 4 conditions)
        ├── A_specific.json
        ├── A_vague.json
        ├── ...
        └── G_verbose.json
```

## Feedback ablation

Studies how different styles of runtime feedback (specific, vague, verbose, null)
affect agent recovery on BFCL multi-turn test cases across 7 failure-pattern
subsets (A-G). Uses the `ExternalFeedbackMiddleware` in `src/wags/middleware/`.

### Running an experiment cell

```bash
python experiments/parth/feedback_ablation/run_experiment.py \
    --subset A --condition specific

# Dry-run to inspect the resolved config and pytest command:
python experiments/parth/feedback_ablation/run_experiment.py \
    --subset A --condition specific --dry-run
```

### Analyzing results

```bash
python experiments/parth/feedback_ablation/analyze_results.py
```

Produces `results_dataframe.csv` (in the feedback_ablation directory) and prints
recovery rate, disruption rate, and behavioral response tables.

## GEPA

Guided Expert Policy Aggregation applied to BFCL instruction optimization.
Uses DSPy's `GEPA` teleprompt to iteratively refine agent instructions.

```bash
python -m experiments.parth.gepa.run \
    --instruction-file path/to/instruction.txt \
    --output-dir outputs/gepa_on_bfcl
```

## Experiment outputs

Raw outputs are gitignored and stored locally under `outputs/` at the repo root:

- `outputs/feedback/` — feedback ablation results (A-G x conditions + baselines)
- `outputs/gepa-expert/` — GEPA optimization artifacts
- `outputs/D_trigger/` — precondition-gated trigger experiment
- `outputs/brake_feedback/` — brake-only feedback pilot

Canonical copies are on Google Drive: *(link TBD)*

## Quarter summary

*(link TBD)*
