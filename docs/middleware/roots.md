# Roots

The MCP `roots` feature enables clients to limit which resources a server can access. The <em class="wags-brand">wags</em> middleware allows methods to be annotated with what resources must be enabled before a tool call be accessed.

## Example

The required root for a function can be configured using the `requires_root` decorator:

```python
from wags.middleware import requires_root, RootsMiddleware

class GithubHandlers:
    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(self, owner: str, repo: str...):
        pass
```

and the `RootsMiddleware` can be enabled in the <em class="wags-brand">wags</em> proxy:

```python
handlers = GitHubHandlers()
mcp.add_middleware(RootsMiddleware(handlers=handlers))
```

Once enabled, agent can only create issues in repositories which the client provides in the roots. 

## API Documentation

::: wags.middleware.roots.requires_root
    options:
      show_source: false
      members: []
      show_signature: false

::: wags.middleware.roots.RootsMiddleware
    options:
      show_source: false
      show_bases: false
      members: []
      show_signature: false
