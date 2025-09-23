# wags 

Model Context Protocol (MCP) offers a standardized way for AI models to interact with external tools and data sources. Yet, as organizations rush to adopt MCP and implement their servers, a critical challenge emerges: we still don't fully understand what makes a good MCP server. While there is significant ongoing research on context engineering and several new MCP features have been proposed to improve user and agent experience, deploying these features in production remains challenging.

The `wags` toolkit is based on state-of-the-art research into how multi-turn agents usually fail, and makes it straightforward to implement advanced countermeasures. The best part is that you don't need to rewrite your existing MCP servers. Instead, you configure `wags` middleware using simple annotations for your server, and it intercepts MCP messages for your goals. You can add `elicitations` for human-in-the-loop confirmations, enforce fine-grained access controls (using `roots`) to make sure your agent doesn't accidentally reveals your private information online, and prevent your agent from repeating the pesky bugs that your agent makes frequently.

## Quick Links

<div class="grid cards" markdown>

- **[Getting Started](quickstart.md)**

    Install `wags` and create your first `wags` enhanced server in minutes

- **[Middleware](middleware/overview.md)**

    Learn about available middleware and how to use them
</div>
