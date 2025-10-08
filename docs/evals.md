# Running Evals

Here's how to run BFCL multi-turn evaluations with <span class="wags-brand">wags</span>.

## Setup

### First Time Setup

If you cloned the repository without submodules:

```bash
# Initialize the data submodule
git submodule update --init --recursive
```

### Updating Data

If you already have the submodule initialized:

```bash
# Update to latest test data
git submodule update --remote
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

## Further Reading

- **BFCL leaderboard**: Visit [gorilla.cs.berkeley.edu](https://gorilla.cs.berkeley.edu/leaderboard.html)
- **Official BFCL repository**: [github.com/ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla)