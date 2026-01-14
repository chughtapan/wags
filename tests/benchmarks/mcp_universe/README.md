# MCP-Universe Repository Management Benchmark Integration

This directory contains the integration of the MCP-Universe repository management benchmark into WAGS.

## Overview

MCP-Universe is a comprehensive benchmark from Salesforce AI Research that evaluates LLMs on realistic tasks using real-world MCP servers. This integration focuses on the repository management domain with:

- 28 GitHub tasks
- Tests realistic GitHub operations including:
  - Creating repositories and branches
  - Managing files and commits
  - Creating pull requests
  - Copying files between repositories
  - Managing issues and labels

## Quick Start

### Prerequisites

1. Docker - Required to run the GitHub MCP server
   - Install Docker Desktop: https://www.docker.com/products/docker-desktop
   - Start Docker Desktop before running tests
   - Verify: `docker --version`
   - Using pinned version v0.15.0 for research reproducibility
   - If you have multiple versions of the GitHub MCP server image, ensure v0.15.0 is tagged as `latest` or is the only version installed

2. GitHub Personal Access Token - For GitHub API access
   - Use a test GitHub account for safety
   - Create token: https://github.com/settings/tokens
   - Required scopes: All scopes

3. LLM API Key

4. Python 3.13+ with [uv](https://docs.astral.sh/uv/)

### Installation

```bash
# Clone the repository
git clone https://github.com/chughtapan/wags.git
cd wags

# Install dependencies
uv pip install -e ".[dev,evals]"

# Pre-pull the GitHub MCP server image
docker pull ghcr.io/github/github-mcp-server:v0.15.0
```

### Environment Variables

```bash
# Required; tests will fail without these
# Use a test GitHub account; the agent performs real operations
export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_token"
export GITHUB_PERSONAL_ACCOUNT_NAME="your_github_username"

# LLM API Key
# For OpenAI models (gpt-5, gpt-4o, gpt-4o-mini, etc.)
export OPENAI_API_KEY="your_openai_key"

# For Anthropic models (claude-sonnet-4-5, etc.)
export ANTHROPIC_API_KEY="your_anthropic_key"
```

### Running Tests

Run all 28 tasks:

```bash
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model gpt-5 -v
```

Run a single task:

```bash
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py::test_mcp_universe[github_task_0001] --model gpt-5 -v
```

Run with different models:

```bash
# GPT-4o
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model gpt-4o

# Claude Sonnet 4.5
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model claude-sonnet-4-5
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--model` | `gpt-4o-mini` | Model to use for the agent |
| `--temperature` | `0.001` | Temperature for LLM sampling |
| `--output-dir` | `outputs` | Base directory for outputs (logs written to `{output_dir}/raw/`) |
| `--validate-only` | - | Skip agent execution, only run evaluation against live GitHub |
| `--toolset` | `full` | Tool availability: `full` (all 93 tools) or `minimal` (19 essential tools) |

### Toolset Comparison

The `--toolset` flag allows comparing agent performance with different tool availability:

```bash
# Full toolset (default): All 93 GitHub MCP tools
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --toolset full -v

# Minimal toolset: 19 essential tools identified from benchmark analysis
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --toolset minimal -v
```

### Validate Mode

Run evaluation against live GitHub without running the agent:

```bash
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --validate-only
```

This is useful if you previously ran the agent and want to re-check the GitHub state (e.g., after fixing an evaluator bug).

## Architecture

### Files

| File | Purpose |
|------|---------|
| `test_mcp_universe.py` | Main pytest test file - agent execution and evaluation |
| `evaluator.py` | Runs MCP-Universe evaluators against test results |
| `evaluator_patch.py` | Patches for GitHub MCP Server v0.15.0 compatibility |
| `fastagent.config.yaml` | FastAgent config for GitHub MCP server (agent) |
| `mcp_server_config.json` | MCP server config for evaluator |
| `instruction.txt` | System instruction for the agent |
| `reporting.py` | Human-readable log formatting |

### MCP Server Configuration

The GitHub MCP server runs in Docker:
- Image: `ghcr.io/github/github-mcp-server:v0.15.0`
- Required env var: `GITHUB_PERSONAL_ACCESS_TOKEN`

Only the access token is passed to the Docker container. The account name is used locally by the evaluator for template substitution in task assertions (e.g., checking `{{GITHUB_PERSONAL_ACCOUNT_NAME}}/repo-name` exists).
