# Running Benchmarks

<em class="wags-brand">wags</em> includes evaluation support for the [Berkeley Function Call Leaderboard (BFCL)](https://gorilla.cs.berkeley.edu/leaderboard.html), enabling systematic testing of LLM function calling capabilities across multi-turn conversations.

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

# Run test category
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

## Test Categories

- **multi_turn_base**: Standard multi-turn function calling (800 tests)
- **multi_turn_miss_func**: Tests handling of missing function scenarios
- **multi_turn_miss_param**: Tests handling of missing parameters
- **multi_turn_long_context**: Context window stress tests with overwhelming information
- **Memory tests**: Tests with key-value, vector, or recursive summarization backends


## Developer Guide

1. **Discovery**: pytest collects tests from `loader.find_all_test_ids()`
2. **Setup**: Creates MCP servers wrapping BFCL API classes using `uv run python`
3. **Execution**: Runs multi-turn conversations with FastAgent
4. **Serialization**: Saves complete message history to `complete.json`
5. **Extraction**: Extracts tool calls from JSON (preserves what FastAgent drops)
6. **Validation**: Uses BFCL validators to check correctness
7. **Result**: Pass/fail based on `validation["valid"]`

## Further Reading

- **Test organization and patterns**: See [tests/README.md](../tests/README.md)
- **BFCL leaderboard**: Visit [gorilla.cs.berkeley.edu](https://gorilla.cs.berkeley.edu/leaderboard.html)
- **Official BFCL repository**: [github.com/ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla)