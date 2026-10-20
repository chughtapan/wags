# Running Evals

Here's how to run benchmark evaluations with <span class="wags-brand">wags</span>. We currently support:
- **BFCL**: Berkeley Function Call Leaderboard multi-turn tests
- **AppWorld**: Realistic task evaluation across 9 day-to-day apps

## Setup

### First Time Setup

```bash
# 1. Initialize the BFCL data submodule
git submodule update --init --recursive

# 2. Install evaluation dependencies
UV_GIT_LFS=1 uv pip install -e ".[dev,evals]"
```

### Updating Data

If you already have the submodule initialized:

```bash
# Update to latest test data
git submodule update --remote
```

### AppWorld Setup

For AppWorld benchmark evaluation:

```bash
# Install evaluation dependencies
UV_GIT_LFS=1 uv pip install -e ".[dev,evals]"

# Initialize AppWorld environment
appworld install

# Download benchmark data
appworld download data
```

## Running Tests

### Basic Usage

```bash
# Run all BFCL multi-turn tests
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py

# Run specific test
.venv/bin/pytest 'tests/benchmarks/bfcl/test_bfcl.py::test_bfcl[multi_turn_base_121]'

# Run test category (multi_turn_base, multi_turn_miss_func, multi_turn_miss_param, multi_turn_long_context)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py -k "multi_turn_miss_func"
```

### With Different Models

`--model` takes any [fast-agent model name](https://fast-agent.ai/models/) (default: `gpt-4o-mini`). Provider keys are read from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc., or from `fastagent.secrets.yaml`.

```bash
# GPT-6.1 Sol
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-6.1-sol

# Claude Opus 5.5 (alias: opus)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model claude-opus-5-5

# Claude Sonnet 5.5 (alias: sonnet)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model claude-sonnet-5-5
```

fast-agent parses the pytest command line in benchmark and e2e tests, and its `-p` (`--prompt-file`) collides with pytest's `-p` plugin flag. Pass pytest plugin options through `PYTEST_ADDOPTS` instead (e.g. `PYTEST_ADDOPTS="-p no:cacheprovider"`).

### Custom Output Directory

```bash
# Save results to specific directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --output-dir outputs/experiment1
```

### Validation Mode

Validate existing logs without running new tests:

**BFCL:**
```bash
# Validate logs (auto-detects from outputs/raw/)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only

# Or specify custom output directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only --output-dir outputs/experiment1
```

**AppWorld:**
```bash
# Validate logs (auto-detects from results/{model}/{dataset}/)
.venv/bin/pytest tests/benchmarks/appworld/test_appworld.py --validate-only --model gpt-6.1-sol --dataset train
```

### AppWorld Results Organization

AppWorld tests automatically organize results during execution:

```bash
# Run tests - results automatically organized
.venv/bin/pytest tests/benchmarks/appworld/test_appworld.py --dataset train --model gpt-6.1-sol

# Results automatically written to:
# - results/gpt-6.1-sol/train/outputs/raw/ (conversation logs)
# - results/gpt-6.1-sol/train/failure_reports/ (auto-generated for failed tests)
# - experiments/outputs/gpt-6.1-sol/train/ (AppWorld evaluation data)

# Clean up large experiment directories after tests
rm -rf experiments/outputs/gpt-6.1-sol/  # Frees ~15GB
```

**AppWorld-specific options:**
```bash
--dataset DATASET         # Dataset: train, dev, test_normal, test_challenge (default: train)
--limit N                 # Run only first N tasks from dataset
--start-from TASK_ID      # Resume from specific task ID
```

### Parallel Execution

Run tests in parallel using multiple workers:

```bash
# Run with 4 workers
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py -n 4

# Run with 8 workers
.venv/bin/pytest tests/benchmarks/appworld/test_appworld.py --dataset train -n 8

# Auto-detect number of CPUs
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py -n auto
```

## Further Reading

### BFCL
- **BFCL leaderboard**: Visit [gorilla.cs.berkeley.edu](https://gorilla.cs.berkeley.edu/leaderboard.html)
- **Official BFCL repository**: [github.com/ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla)

### AppWorld
- **AppWorld Website**: [appworld.dev](https://appworld.dev/)
- **AppWorld GitHub**: [github.com/StonyBrookNLP/appworld](https://github.com/StonyBrookNLP/appworld)
- **AppWorld Paper**: [arxiv.org/abs/2407.18901](https://arxiv.org/abs/2407.18901)