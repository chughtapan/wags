# Quick Start Guide

Get started with <span class="wags-brand">wags</span> by connecting to existing wags servers.

## Prerequisites

- Python 3.13.5 or higher
- [`uv` package manager](https://docs.astral.sh/uv/getting-started/installation/)

## Installation

> ⚠️ **Warning**: <span class="wags-brand">wags</span> is based on ongoing research and is under active development. Features and APIs may change. Some experimental MCP features are only supported in our fork of [fast-agent](https://github.com/chughtapan/fast-agent) included with <span class="wags-brand">wags</span>.

```bash
# Clone the repository
git clone https://github.com/chughtapan/wags.git
cd wags

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install the package in development mode
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

## Getting Started

The easiest way to connect to wags servers is using the `wags run` command:

```bash
# Connect to all configured servers
wags run

# Connect to specific servers only
wags run --servers github

# Use a different model
wags run --model claude-3-5-sonnet-20241022
```

`wags run` invokes fast-agent with a configuration file ([`servers/fastagent.config.yaml`](https://github.com/chughtapan/wags/blob/main/servers/fastagent.config.yaml)) and basic instructions ([`src/wags/utils/agent_instructions.txt`](https://github.com/chughtapan/wags/blob/main/src/wags/utils/agent_instructions.txt)), and connects to all servers by default. You can configure which servers to connect to using the `--servers` flag or create your own configuration and instruction files - see the [fast-agent documentation](https://github.com/chughtapan/fast-agent) for more details.

## Next Steps

- **[Onboarding New Servers](onboarding.md)** - Create your own wags server with middleware
- **[Middleware Overview](middleware/overview.md)** - Understand available middleware features
