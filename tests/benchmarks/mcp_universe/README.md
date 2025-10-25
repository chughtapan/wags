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

1. **Docker** - REQUIRED to run the GitHub MCP server
   - Install Docker Desktop: https://www.docker.com/products/docker-desktop
   - **Start Docker Desktop** before running tests
   - Verify installation: `docker --version`
   - **Note**: Using pinned version v0.15.0 for research reproducibility (before PR #1091 which added automatic instruction generation)
   - If `docker` command is not found, ensure Docker Desktop is running and restart your terminal
2. **GitHub Personal Access Token** - For GitHub API access
   - **CRITICAL**: Use a dedicated test GitHub account for safety
   - Create token: https://github.com/settings/tokens
3. **OpenAI API Key** (or Anthropic for Claude models) - For running the LLM agent
4. **Python 3.13+** with [uv](https://docs.astral.sh/uv/)

### Installation

```bash
# Clone the repository (if not already done)
git clone https://github.com/chughtapan/wags.git
cd wags

# Install dependencies (pulls the forked MCP-Universe package via eval extras)
uv sync --extra evals

# (optional) Install dev tooling alongside eval extras
uv sync --extra dev --extra evals

# Verify Docker is working
docker run --rm hello-world

# Pre-pull the GitHub MCP server image (recommended for faster test startup)
docker pull ghcr.io/github/github-mcp-server:v0.15.0
```

**Note**: The `--extra evals` flag installs:
- `mcpuniverse` from the fork [`vinamra57/MCP-Universe@72389d8`](https://github.com/vinamra57/MCP-Universe/tree/72389d8a04044dceb855f733a938d0344ac58813), which removes heavy 3D dependencies while keeping the repository-management configs
- `bfcl-eval` for Berkeley Function Call Leaderboard evaluation
- Other shared evaluation dependencies

All repository management task JSON files are bundled inside the installed `mcpuniverse` wheel, so no git submodules or manual data checkout are required.

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
