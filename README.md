# Welcome to wags

<img src="docs/assets/images/wags-logo.png" alt="WAGS Logo" width="110" align="left" style="margin-right: 20px;">

The <b style="font-family: Helvetica, Arial, sans-serif; font-weight: bold; letter-spacing: -0.02em;">wags</b> toolkit is based on state-of-the-art research into how multi-turn agents usually fail, and makes it straightforward to implement advanced countermeasures. While Model Context Protocol (MCP) offers a standardized way for AI models to interact with external tools and data sources, we still don't fully understand what makes a good MCP server. <b style="font-family: Helvetica, Arial, sans-serif; font-weight: bold; letter-spacing: -0.02em;">wags</b> makes it easy to deploy the latest research on context engineering and several new MCP features improve user and agent experience without rewriting your existing MCP servers.

> ⚠️ **Warning**: <b style="font-family: Helvetica, Arial, sans-serif; font-weight: bold; letter-spacing: -0.02em;">wags</b> is based on ongoing research and is under active development. Features and APIs may change. Some experimental MCP features are only supported in our fork of [fast-agent](https://github.com/chughtapan/fast-agent) included with <b style="font-family: Helvetica, Arial, sans-serif; font-weight: bold; letter-spacing: -0.02em;">wags</b>.

<div style="clear: both;"></div>

## Prerequisites

- Python 3.13.5 or higher
- [`uv` package manager](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or `pip`
- Basic understanding of [MCP (Model Context Protocol)](https://modelcontextprotocol.io/docs/getting-started/intro)
- An existing MCP server to work with

## Installation

```bash
# Clone the repository
git clone https://github.com/chughtapan/wags.git
cd wags

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install with dev dependencies (for testing and linting)
uv pip install -e ".[dev]"
```

### Verify Installation

```bash
wags version
```

You should see:
```
WAGS version 0.1.0
FastMCP version x.x.x
```

## Quick Start

### Connect to Existing Servers

```bash
# Connect to all configured servers
wags run

# Connect to specific servers
wags run --servers github
```

See the [Quick Start Guide](https://chughtapan.github.io/wags/quickstart/) for details.

### Onboarding New Servers

To wrap your own MCP server with <b style="font-family: Helvetica, Arial, sans-serif; font-weight: bold; letter-spacing: -0.02em;">wags</b> middleware, see the [Onboarding Guide](https://chughtapan.github.io/wags/onboarding/) for step-by-step instructions.

**Example:** Check out `servers/github/` for a complete implementation.

## Project Structure

```
src/
└── wags/                     # WAGS middleware framework
    ├── cli/                  # CLI commands using cyclopts
    │   └── main.py           # wags CLI entry point
    ├── middleware/           # Middleware implementations
    │   ├── base.py           # Base middleware abstract class
    │   ├── elicitation.py    # Parameter elicitation middleware
    │   ├── roots.py          # Access control middleware
    │   └── todo.py           # Task tracking server
    ├── templates/            # Jinja2 templates for code generation
    │   ├── handlers.py.j2    # Handlers class template
    │   └── main.py.j2        # Main file template
    ├── utils/                # Utility modules
    │   ├── config.py         # Configuration management
    │   ├── handlers_generator.py  # Generate handler stubs from MCP
    │   └── server.py         # Server discovery and running
    └── proxy.py              # Proxy server for middleware chain
```

## Features

### Task Tracking

Enable automatic task tracking for LLM agents with built-in TodoWrite and TodoRead tools:

```python
from wags.proxy import create_proxy

proxy = create_proxy(server, enable_todos=True)
```

This provides LLMs with tools to break down complex tasks and track progress. See the [Todo Integration Guide](https://chughtapan.github.io/wags/middleware/todo/) for details.

### Middleware

For detailed middleware documentation, see the [full documentation](https://chughtapan.github.io/wags/).

## Documentation

### View Documentation Online
Visit [https://chughtapan.github.io/wags/](https://chughtapan.github.io/wags/) for the full documentation.

### Build Documentation Locally
```bash
# Build documentation
mkdocs build

# Serve documentation locally
mkdocs serve
```

## Development

### Testing
```bash
# Run all unit tests (excludes benchmarks by default)
.venv/bin/pytest tests/

# Run unit tests with coverage
.venv/bin/pytest tests/unit/ -v

# Run integration tests
.venv/bin/pytest tests/integration/ -v
```

### Code Quality
```bash
# Run linter
.venv/bin/ruff check src/ tests/ servers/

# Fix linting issues
.venv/bin/ruff check src/ tests/ servers/ --fix

# Format code
.venv/bin/ruff format src/ tests/ servers/

# Run type checking
.venv/bin/mypy src/ servers/ tests/

# Install pre-commit hooks
pre-commit install

# Run pre-commit hooks manually
pre-commit run --all-files
```

## Running Benchmarks

WAGS includes evaluation support for:
- **BFCL**: Berkeley Function Call Leaderboard
- **AppWorld**: Realistic task evaluation across 9 day-to-day apps

### BFCL Setup
First, install the evaluation dependencies:

```bash
# 1. Initialize the data submodules
git submodule update --init --recursive

# 2. Install evaluation dependencies
uv pip install -e ".[dev,evals]"
```

### AppWorld Setup

```bash
# Install evaluation dependencies
UV_GIT_LFS=1 uv pip install -e ".[dev,evals]"

# Initialize AppWorld environment
appworld install

# Download benchmark data
appworld download data
```

### Run Benchmark Tests

**BFCL:**
```bash
# Run all BFCL tests
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py

# Run specific test
.venv/bin/pytest 'tests/benchmarks/bfcl/test_bfcl.py::test_bfcl[multi_turn_base_121]'

# Run with specific model
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-4o
```

**AppWorld:**
```bash
# Run all train tasks
.venv/bin/pytest tests/benchmarks/appworld/test_appworld.py --dataset train --model gpt-4o

# Run specific task
.venv/bin/pytest 'tests/benchmarks/appworld/test_appworld.py::test_appworld[train_001]'
```

For detailed information, see:
- **Evaluation guide**: [docs/evals.md](https://chughtapan.github.io/wags/evals/)
- **Test organization and patterns**: [tests/README.md](tests/README.md)

## License

Apache 2.0
