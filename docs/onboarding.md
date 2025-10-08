# Onboarding New Servers

Learn how to create a <span class="wags-brand">wags</span> proxy server that wraps existing MCP servers with middleware.

## Prerequisites

- <span class="wags-brand">wags</span> installed (see [Quick Start](quickstart.md) for installation)
- Basic understanding of [MCP (Model Context Protocol)](https://modelcontextprotocol.io/docs/getting-started/intro)
- An existing MCP server to work with

## Creating a <span class="wags-brand">wags</span> Proxy Server

<span class="wags-brand">wags</span> provides the `quickstart` command to generate proxy servers that wrap existing MCP servers with middleware.

!!! tip "Complete Example Available"
    The complete implementation for the [GitHub MCP Server](https://github.com/github/github-mcp-server) is in `servers/github/`.

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
# Run directly
python main.py

# Or use wags start-server
wags start-server servers/your-server
```

Your proxy server is now running!

### Step 6 (Optional): Add to Shared Configuration

To use your server with `wags run`, add it to `servers/fastagent.config.yaml`:

```yaml
mcp:
  servers:
    your-server:
      transport: stdio
      command: wags
      args:
        - start-server
        - servers/your-server
      env:
        API_KEY: ${YOUR_API_KEY}
      roots:
        - uri: https://example.com/allowed
          name: "Allowed Resources"
```

Now you can connect to your server with:

```bash
wags run --servers your-server
```

## Learn More

- **[Middleware Overview](middleware/overview.md)** - Understand how middleware works
- **[Roots](middleware/roots.md)** - Access control with URI templates
- **[Elicitation](middleware/elicitation.md)** - Parameter review and collection
