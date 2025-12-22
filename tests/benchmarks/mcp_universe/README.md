# MCP-Universe Repository Management Benchmark Integration

This directory contains the integration of the MCP-Universe repository management benchmark into WAGS.

## Overview

MCP-Universe is a comprehensive benchmark from Salesforce AI Research that evaluates LLMs on realistic tasks using real-world MCP servers. This integration focuses on the **repository management domain** with:

- **28 pure GitHub tasks** (github_task_0001 through github_task_0030, excluding 0013 and 0020)
- Tests realistic GitHub operations including:
  - Creating repositories and branches
  - Managing files and commits
  - Creating pull requests
  - Copying files between repositories
  - Managing issues and labels

## Quick Start

### Prerequisites

1. **Docker** - Required to run the GitHub MCP server
   - Install Docker Desktop: https://www.docker.com/products/docker-desktop
   - **Start Docker Desktop** before running tests
   - Verify: `docker --version`
   - Using pinned version v0.15.0 for research reproducibility

2. **GitHub Personal Access Token** - For GitHub API access
   - **CRITICAL**: Use a dedicated test GitHub account for safety
   - Create token: https://github.com/settings/tokens
   - Required scopes: `repo`, `delete_repo`

3. **LLM API Key**
   - OpenAI API key for GPT models, OR
   - Anthropic API key for Claude models

4. **Python 3.13+** with [uv](https://docs.astral.sh/uv/)

### Installation

```bash
# Clone the repository
git clone https://github.com/chughtapan/wags.git
cd wags

# Install base dependencies
uv sync

# Install mcpuniverse from the wags-dev branch
uv pip install "mcpuniverse @ git+https://github.com/vinamra57/MCP-Universe.git@wags-dev"

# Pre-pull the GitHub MCP server image
docker pull ghcr.io/github/github-mcp-server:v0.15.0
```

**Note**: The `wags-dev` branch of MCP-Universe removes `mathutils` (fails to build on Python 3.13 due to removed private API `_PyLong_AsInt`) and fixes package data glob patterns to include nested benchmark configs.

### Environment Variables

**Required** - tests will fail without these:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_token"
export GITHUB_PERSONAL_ACCOUNT_NAME="your_github_username"
```

**LLM API Key** - one of these depending on model:

```bash
# For OpenAI models (gpt-4o, gpt-4o-mini, etc.)
export OPENAI_API_KEY="your_openai_key"

# For Anthropic models (claude-sonnet-4-5, etc.)
export ANTHROPIC_API_KEY="your_anthropic_key"
```

**IMPORTANT**: Use a dedicated test GitHub account. The agent performs real operations including creating and deleting repositories.

### Running Tests

Run all 28 tasks:

```bash
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model gpt-4o-mini -v
```

Run a single task:

```bash
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py::test_mcp_universe[github_task_0001] --model gpt-4o-mini -v
```

Run with different models:

```bash
# GPT-4o
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model gpt-4o

# Claude Sonnet
pytest tests/benchmarks/mcp_universe/test_mcp_universe.py --model claude-sonnet-4-5
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--model` | `gpt-4o-mini` | Model to use for the agent |
| `--temperature` | `0.001` | Temperature for LLM sampling |
| `--output-dir` | `outputs` | Base directory for outputs (logs written to `{output_dir}/raw/`) |
| `--validate-only` | - | Skip agent execution, only run evaluation against live GitHub |

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

### Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | MCP Server, Evaluator | GitHub API authentication |
| `GITHUB_PERSONAL_ACCOUNT_NAME` | Evaluator | Template substitution in task assertions |
| `OPENAI_API_KEY` | FastAgent | OpenAI model access |
| `ANTHROPIC_API_KEY` | FastAgent | Anthropic model access |

### MCP Server Configuration

The GitHub MCP server runs in Docker:
- Image: `ghcr.io/github/github-mcp-server:v0.15.0`
- Required env var: `GITHUB_PERSONAL_ACCESS_TOKEN`

Only the access token is passed to the Docker container. The account name is used locally by the evaluator for template substitution in task assertions (e.g., checking `{{GITHUB_PERSONAL_ACCOUNT_NAME}}/repo-name` exists).

## Troubleshooting

### "Docker not found"
Ensure Docker Desktop is running and restart your terminal.

### "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set"
Export the required environment variables before running tests.

### "repository doesn't exist" (false negative)
GitHub's search API has indexing delays for newly created repos. The evaluator patches handle this with direct API calls, but occasional failures may occur.

### Rate limiting
If you hit GitHub API rate limits, wait a few minutes or use a token with higher limits.

### Tests pass but some checks fail
Review the `*_readable.log` files in the output directory for detailed execution traces.
