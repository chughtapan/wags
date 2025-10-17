# MCP-Universe Repository Management Benchmark Integration

This directory contains the integration of the MCP-Universe repository management benchmark into WAGS.

## Overview

MCP-Universe is a comprehensive benchmark from Salesforce AI Research that evaluates LLMs on realistic tasks using real-world MCP servers. This integration focuses on the **repository management domain**, which includes 28 tasks testing GitHub operations like:

- Creating repositories and branches
- Managing files and commits
- Creating pull requests
- Copying files between repositories
- Managing issues and labels

## Quick Start

### Prerequisites

1. **Node.js and npx** - Required to run the GitHub MCP server
2. **GitHub Personal Access Token** - For GitHub API access
3. **OpenAI API Key** - For running the LLM agent
4. **Python 3.13+** with uv

### Installation

```bash
# Clone the repository (if not already done)
git clone https://github.com/chughtapan/wags.git
cd wags

# Initialize submodules (includes MCP-Universe data)
git submodule update --init --recursive

# Install dependencies
uv sync --extra evals

# Install additional MCP-Universe evaluator dependencies
uv pip install yfinance playwright blender-mcp google-api-python-client wikipedia-api
```

### Configuration

Set the required environment variables:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_token_here"
export GITHUB_PERSONAL_ACCOUNT_NAME="your_github_username"
export OPENAI_API_KEY="your_openai_key_here"
```

**IMPORTANT**: Use a dedicated test GitHub account. The AI agent will perform real operations on GitHub repositories.

### Running Tests

Run all 28 repository management tasks:

```bash
uv run pytest tests/benchmarks/mcp_universe/test_mcp_universe.py \
    --model gpt-4o-mini \
    --output-dir outputs/mcp_universe \
    -v
```

Run a single task:

```bash
uv run pytest tests/benchmarks/mcp_universe/test_mcp_universe.py::test_mcp_universe[github_task_0001] \
    --model gpt-4o-mini \
    --output-dir outputs/mcp_universe \
    -v
```

Run with different models:

```bash
# Use GPT-4o
uv run pytest tests/benchmarks/mcp_universe/test_mcp_universe.py \
    --model gpt-4o \
    --output-dir outputs/mcp_universe

# Use Claude (requires ANTHROPIC_API_KEY)
uv run pytest tests/benchmarks/mcp_universe/test_mcp_universe.py \
    --model claude-3-5-sonnet-20241022 \
    --output-dir outputs/mcp_universe
```

### Validate Mode

If you have existing output files, you can validate them without re-running the agent:

```bash
uv run pytest tests/benchmarks/mcp_universe/test_mcp_universe.py \
    --validate-only \
    --log-dir outputs/mcp_universe/raw \
    --output-dir outputs/mcp_universe
```
