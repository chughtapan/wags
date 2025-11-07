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
# Run first task from train dataset
pytest tests/benchmarks/appworld/test_appworld.py --dataset train --limit 1 --model gpt-4o

# Run first 5 train tasks
pytest tests/benchmarks/appworld/test_appworld.py --dataset train --limit 5

# Run all dev tasks
pytest tests/benchmarks/appworld/test_appworld.py --dataset dev --model gpt-4o

# Run specific task (use actual task IDs like 82e2fac_1, not train_001)
pytest 'tests/benchmarks/appworld/test_appworld.py::test_appworld[82e2fac_1]'

# Validate existing results without re-running
pytest tests/benchmarks/appworld/test_appworld.py --validate-only
```

## CLI Options

### Dataset Selection
```bash
--dataset {train,dev,test_normal,test_challenge}  # Default: train
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

### Parallel Execution
```bash
-n 4     # Run with 4 workers
-n 8     # Run with 8 workers
-n auto  # Auto-detect number of CPUs
```

Example: `pytest tests/benchmarks/appworld/test_appworld.py --dataset train -n 4`

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

## Debugging

### Inspect Test Output
```bash
# Structured logs
cat outputs/raw/<task_id>_structured.jsonl

# Complete message history
cat outputs/raw/<task_id>_complete.json
```
