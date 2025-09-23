# Elicitation

Whenever I've tried to use my LLM to create git commits or pull requests or something like that, I hate it's writing style. I frequently find myself spending more time trying to instruct the model properly than I would've required to edit the message myself. The MCP `elicitation` feature enables servers to request additional information from the users for specific tasks, for instance while executing tools. The `ElicitationMiddleware` in <span class="wags-brand">wags</span> uses this to improve the user experience for such tools where users might want to edit the models generation before executing them directly.

## Example

`RequiresElicitation` type annotation on on tool parameters informs <span class="wags-brand">wags</span> middleware which values should be reviewed by users.

```python linenums="1" title="handlers.py"
from typing import Annotated
from wags.middleware import ElicitationMiddleware, RequiresElicitation

class GithubHandlers:
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: Annotated[str, RequiresElicitation(
            "Issue Title"
        )],
        body: Annotated[str, RequiresElicitation(
            "Issue Body"
        )]
    ):
        pass
```

and the `ElicitationMiddleware` can be enabled in the <span class="wags-brand">wags</span> proxy:

```python title="main.py"
handlers = GithubHandlers()
mcp.add_middleware(ElicitationMiddleware(handlers=handlers))
```

Now whenever a tool with elicitation annotations is triggered, <span class="wags-brand">wags</span> will intercept the tool call, allow the user to edit those arguments, and then make the upstream `tool` call. So you can be confident that your agent doesn't cause embarrassment for you

## API Documentation

::: wags.middleware.elicitation.RequiresElicitation
    options:
      show_source: false
      members: []
      show_signature: false

::: wags.middleware.elicitation.ElicitationMiddleware
    options:
      show_source: false
      show_bases: false
      members: []
      show_signature: false

