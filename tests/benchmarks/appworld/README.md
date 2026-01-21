# AppWorld Benchmark

## Install AppWorld

```bash
# Install evaluation dependencies
UV_GIT_LFS=1 uv pip install -e ".[dev,evals]"

# Initialize AppWorld environment (unpacks encrypted code)
appworld install

# Download benchmark data (if not already present)
appworld download data
```

## Run Tests

```bash
# Run first task (uses default: train,dev datasets, organized to results/gpt-4o/train_dev/)
pytest tests/benchmarks/appworld/test_appworld.py --limit 1 --model gpt-4o

# Run only train dataset
pytest tests/benchmarks/appworld/test_appworld.py --datasets train --limit 5 --model gpt-4o

# Run only dev dataset
pytest tests/benchmarks/appworld/test_appworld.py --datasets dev --model gpt-4o

# Run multiple datasets
pytest tests/benchmarks/appworld/test_appworld.py --datasets train,dev,test_normal

# Run specific task (use actual task IDs like 82e2fac_1, not train_001)
pytest 'tests/benchmarks/appworld/test_appworld.py::test_appworld[82e2fac_1]'

# Validate existing results (auto-detects from results/gpt-4o/train/)
pytest tests/benchmarks/appworld/test_appworld.py --validate-only --model gpt-4o --datasets train
```

## CLI Options

### Dataset Selection
```bash
--datasets train                    # Single dataset
--datasets train,dev                # Multiple datasets (default)
--datasets train,dev,test_normal    # Run train, dev, and test_normal
```
- `train`: Training dataset (90 tasks)
- `dev`: Development/validation dataset
- `test_normal`: Standard test set
- `test_challenge`: Challenging test set

### Test Limits
```bash
--limit N  # Only run first N tasks from dataset
```

### Model Selection
```bash
--model gpt-4o  # LLM model to use (default: gpt-4o-mini)
--temperature 0.001  # Temperature for sampling (default: 0.001)
```

### Prompt Mode
```bash
# Default: zero-shot (no examples in prompt)
pytest tests/benchmarks/appworld/test_appworld.py --datasets train

# Few-shot: include worked-out examples in system prompt
pytest tests/benchmarks/appworld/test_appworld.py --datasets train --default-few-shot
```

### Parallel Execution
```bash
-n 4     # Run with 4 workers
-n 8     # Run with 8 workers
-n auto  # Auto-detect number of CPUs
```

Example: `pytest tests/benchmarks/appworld/test_appworld.py --datasets train -n 4`

## File Structure

```
tests/benchmarks/appworld/
├── mcp_server.py               # Custom MCP wrapper (accepts task_id)
├── appworld_helpers.py         # API prediction and instruction loading
├── test_appworld.py            # Pytest test cases and evaluation
├── fastagent.config.yaml       # MCP connection config (uses env vars)
├── conftest.py                 # Pytest fixtures (dataset, limit, api_mode)
├── system_instruction.txt      # Agent system instructions template
└── README.md                   # This file
```

## Evaluation Process

1. **Agent Execution**: Agent interacts with apps via MCP tools
2. **Task Completion**: Agent calls `apis.supervisor.complete_task()`
3. **State Capture**: Final database state is saved
4. **Validation**: AppWorld evaluator compares DB state to ground truth
5. **Result**: Pass/fail based on whether task requirements were met

## Results Organization

AppWorld tests automatically organize results during execution:

```
results/{model}/{dataset}/
├── outputs/
│   └── raw/
│       ├── {task_id}_complete.json      # Conversation logs
│       └── {task_id}_structured.jsonl   # Turn-by-turn events
└── failure_reports/
    └── failure_report_{task_id}.md      # Auto-generated for failed tests

experiments/outputs/{model}/{dataset}/    # AppWorld evaluation data (~15GB)
└── tasks/{task_id}/
    ├── dbs/                              # Database snapshots
    └── evaluation/
        └── report.md                     # Evaluation results
```

### Cleanup

After tests complete, clean up large experiment directories:

```bash
rm -rf experiments/outputs/gpt-4o/  # Frees ~15GB
```

## Debugging

### Inspect Test Output
```bash
# Structured logs
cat results/gpt-4o/train/outputs/raw/<task_id>_structured.jsonl

# Complete message history
cat results/gpt-4o/train/outputs/raw/<task_id>_complete.json

# Failure report (auto-generated for failed tests)
cat results/gpt-4o/train/failure_reports/failure_report_<task_id>.md
```
