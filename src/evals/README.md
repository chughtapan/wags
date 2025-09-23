# Evaluation Framework for Fast-Agent

A pytest-based evaluation framework for testing LLM function calling capabilities using the Berkeley Function Call Leaderboard (BFCL) with fast-agent and MCP servers.

## Installation

> ⚠️ **Warning**: This evaluation framework is based on ongoing research and is under active development. Features and APIs may change.

```bash
# From the project root directory (assuming wags is already cloned)
# Create and activate virtual environment if not already done
uv venv
source .venv/bin/activate

# Install the wags package with dev dependencies
uv pip install -e ".[dev]"

# Install BFCL (without heavy dependencies) - MUST be done after main install
cd submodules/bfcl/berkeley-function-call-leaderboard
uv pip install --no-deps -e .
cd ../../..
```

## Usage

### Running Tests with Pytest

```bash
# Run all multi-turn tests
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py

# Run specific test
.venv/bin/pytest 'tests/benchmarks/bfcl/test_bfcl.py::test_bfcl[multi_turn_base_55]'

# Run category of tests
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py -k "multi_turn_base"

# Run with different model
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-4o

# Save outputs to specific directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --output-dir outputs/experiment1

# Validate existing logs only (no new runs)
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only

# Validate logs from specific directory
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only --log-dir outputs/experiment1/raw
```

## Architecture

```
src/evals/
├── core/                       # Generic evaluation framework
│   ├── runner.py              # Generic async test execution
│   ├── serializer.py          # Preserves tool calls FastAgent drops
│   └── logger.py              # Typed event logging (replaces string matching)
└── benchmarks/                 # Benchmark implementations
    └── bfcl/                  # BFCL-specific implementation
        ├── loader.py          # Data loading (currently multi_turn only)
        ├── evaluator.py       # BFCL validation logic
        ├── mcp_server.py      # MCP wrapper for BFCL APIs
        ├── elicitation.py     # Ground truth elicitation handler
        ├── config.yaml        # MCP server configuration
        └── instruction.txt    # System prompt

tests/
├── conftest.py                # Pytest fixtures and configuration
├── benchmarks/
│   └── bfcl/
│       └── test_bfcl.py      # Async test implementation
└── unit/
    └── core/
        └── test_serializer.py # Unit tests for serialization

submodules/
└── bfcl/                      # BFCL git submodule
```

## How It Works

1. **Test Discovery**: pytest dynamically discovers tests from BFCL data files
2. **Async Execution**: Tests run as native async functions using pytest-asyncio
3. **MCP Server Setup**: Wraps BFCL API classes as MCP servers for fast-agent
4. **Execution**: Runs tests, serializes complete message history to `complete.json`
5. **Extraction**: Extracts tool calls directly from `complete.json` (no JSONL parsing)
6. **Evaluation**: Uses BFCL's validators to check correctness
7. **Pass/Fail**: Only `validation["valid"]` determines test outcome (ignores irrelevance checks)

## Key Features

- **Pytest-native**: No CLI, pure pytest with async support
- **Two modes**: Run new tests OR validate from `complete.json` with `--validate-only`
- **Tool call preservation**: MessageSerializer preserves tool calls that FastAgent drops
- **Single extraction path**: Both run and validate modes use same JSON extraction
- **Structured logging**: Typed events replace fragile string matching in logs
- **Minimal storage**: Only saves `complete.json` (extracts tool calls on-demand)
- **Clean architecture**: Generic runner, benchmark-specific logic isolated in bfcl/
- **Pattern matching**: Use pytest's `-k` flag for test selection
- **Sequential by default**: No concurrency issues, no rate limiting problems
- **Extensible**: Easy to add new benchmarks (copy bfcl/ folder pattern)

## Output Structure

```
outputs/
├── configs/                 # Generated YAML configs
├── raw/                     # JSONL logs from fast-agent
│   ├── *_fastagent.jsonl   # Raw conversation logs
│   ├── *_detailed.json     # Structured message history
│   └── *_complete.json     # Standard format
└── evaluations/            # Evaluation results
    └── *.json              # Validation results per test
```

## License

Apache 2.0