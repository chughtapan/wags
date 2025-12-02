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

```bash
# Use GPT-4o (default)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-4o

# Use Claude
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model claude-3-5-sonnet-20241022

# Use GPT-4o-mini
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-4o-mini
```

### Custom Output Directory

```bash
# Save results to specific directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --output-dir outputs/experiment1
```

### Validation Mode

Validate existing logs without running new tests:

```bash
# Validate logs from default directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only

# Validate logs from specific directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only --log-dir outputs/experiment1/raw
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