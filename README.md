# BFCL Evaluation for Fast-Agent

A clean evaluation framework for testing LLM function calling capabilities using the Berkeley Function Call Leaderboard (BFCL) with fast-agent and MCP servers.

## Installation

```bash
# Install BFCL (without heavy dependencies)
cd bfcl/berkeley-function-call-leaderboard
uv pip install --no-deps -e .

# Install this package
cd ../..
uv pip install -e .
```

## Usage

### Command Line Interface

```bash
# Run a single test
elicitation-evals test multi_turn_base_55 --model gpt-4o-mini

# Run with different model
elicitation-evals test multi_turn_base_55 --model gpt-4.1

# Evaluate existing results
elicitation-evals evaluate multi_turn_base_55 outputs/raw/multi_turn_base_55_fastagent.jsonl
```

### Python API

```python
from elicitation_evals.runner import run_test
from elicitation_evals.evaluator import evaluate_results
from elicitation_evals.bfcl.data_loader import load_test_entry

# Load and run a test
test_case = load_test_entry("multi_turn_base_55")
result = run_test(test_case, model="gpt-4o-mini")

# Evaluate results
if result["success"]:
    evaluation = evaluate_results("multi_turn_base_55", result["output_file"])
    print(f"Validation: {evaluation['validation']['valid']}")
    print(f"Irrelevance: {evaluation['irrelevance_check']['valid']}")
```

## Architecture

```
src/elicitation_evals/
├── __main__.py              # CLI entry point
├── runner.py                # Test execution logic
├── evaluator.py             # Evaluation logic
├── parser.py                # JSONL log parsing
├── config.py                # Config/script generation
├── bfcl/                    # BFCL-specific code
│   ├── data_loader.py       # BFCL data loading
│   └── mcp_server.py        # MCP wrapper for BFCL APIs
└── templates/               # Jinja2 templates
    ├── config.yaml.j2       # Fast-agent YAML config
    ├── script.py.j2         # Python script template
    └── system_prompt.j2     # System prompt template
```

## How It Works

1. **Test Loading**: Loads BFCL test cases with function definitions and multi-turn conversations
2. **MCP Server Setup**: Wraps BFCL API classes as MCP servers for fast-agent
3. **Script Generation**: Creates fast-agent scripts using Jinja2 templates
4. **Execution**: Runs tests capturing all tool calls in JSONL logs
5. **Parsing**: Extracts tool calls from logs with proper turn detection
6. **Evaluation**: Uses BFCL's validators to check correctness

## Key Features

- **Clean architecture**: Core logic separate from BFCL-specific code
- **Proper packaging**: Installable via pip/uv with CLI commands
- **Template-based**: System prompts and scripts in Jinja2 templates
- **Turn detection**: Correctly identifies conversation boundaries using `finish_reason="stop"`
- **Type conversion**: Handles BFCL→OpenAI type mappings (dict→object, float→number)
- **Extensible**: Easy to add custom data sources and MCP servers

## Development

```bash
# Run tests on specific range
for i in {50..60}; do
    elicitation-evals test multi_turn_base_$i --model gpt-4o-mini
done

# Evaluate individual results
elicitation-evals evaluate multi_turn_base_55 outputs/raw/multi_turn_base_55_fastagent.jsonl
```

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

MIT