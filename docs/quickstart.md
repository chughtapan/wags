# Quick Start Guide

Get up and running with <span class="wags-brand">wags</span> in just a few minutes. This guide will walk you through installation and creating a proxy server with middleware for existing MCP servers.

## Prerequisites

- Python 3.13.5 or higher
- [`uv` package manager](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or `pip`
- Basic understanding of [MCP (Model Context Protocol)](https://modelcontextprotocol.io/docs/getting-started/intro)
- An existing MCP server to work with

## Installation

> ⚠️ **Warning**: <span class="wags-brand">wags</span> is based on ongoing research and is under active development. Features and APIs may change.

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

## Creating a <span class="wags-brand">wags</span> Proxy Server

<span class="wags-brand">wags</span> provides the `quickstart` command to generate proxy servers that wrap existing MCP servers with middleware.

### Step 1: Prepare Your MCP Server Configuration

Create a configuration file that describes your MCP server. Save it as `config.json`:

```json title="config.json"
--8<-- "snippets/quickstart/config.json"
```

### Step 2: Generate the Proxy Server

Use the `quickstart` command to generate middleware handlers and main file:

```bash
# Generate both handlers and main files
wags quickstart config.json

# Or with custom file names
wags quickstart config.json \
  --handlers-file github_handlers.py \
  --main-file github_proxy.py
```

### Step 3: Add Middleware Decorators

Edit the generated handlers file to add middleware decorators:

```python linenums="1" title="handlers.py"
--8<-- "snippets/quickstart/handlers.py"
```

### Step 4: Attach Middleware to your MCP Server

The automatically generated main.py includes (commented) code to attach <span class="wags-brand">wags</span> middleware to your MCP server. You should edit the file to uncomment the middleware you need:

```python linenums="1" title="main.py"
--8<-- "snippets/quickstart/main.py"
```

### Step 5: Run Your Proxy Server

```bash
python main.py 
```

Your proxy server is now running! 

## Learn More

- **[Middleware Overview](middleware/overview.md)** - Understand how middleware works
- **[Roots](middleware/roots.md)** - Access control with URI templates
- **[Elicitation](middleware/elicitation.md)** - Parameter review and collection
