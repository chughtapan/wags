# The Motivation Behind WAGS

## The AI Agent Revolution and Its Growing Pains

As we stand at the cusp of 2025, AI agents equipped with tool-calling capabilities have moved from experimental prototypes to production systems. 

This uncertainty isn't merely academic. It manifests as real production failures, security vulnerabilities, and poor user experiences that cost organizations time, money, and trust. WAGS (Web Agent Gateway System) was born from extensive research into these failure patterns and a recognition that the solution lies not in perfect server implementations, but in intelligent middleware orchestration.

## Understanding the Core Challenges

### The Context Rot Problem

Modern LLMs promise million-token context windows, suggesting that more information should lead to better results. Yet research from Chroma and others reveals a troubling phenomenon known as context rot. As input length grows, model performance degrades dramatically. Models that achieve 95% accuracy on short prompts fall to 60-70% when dealing with longer contexts containing distractors and irrelevant information. The degradation isn't linear—it's often sudden and catastrophic, with models losing track of critical information buried in the middle of their context window.

This creates a fundamental paradox for MCP servers. Each tool added to a server increases the context burden, as every interaction requires the model to process all tool names, descriptions, and parameters. A comprehensive GitHub MCP server might expose dozens of endpoints for different operations, but this abundance becomes a liability. Agents begin hallucinating tool calls to non-existent endpoints, selecting incorrect parameters from confusion, and exhibiting degraded reasoning as their context windows fill with tool specifications. The result is slower, more expensive operations that paradoxically become less reliable as more capabilities are added.

### The MCP vs API Impedance Mismatch

As Jeremiah Lowin astutely observes in his analysis, blindly converting REST APIs to MCP servers is a recipe for failure. REST APIs were designed for programmatic access—atomic, stateless operations that computers execute efficiently. Agents, however, operate fundamentally differently. Each tool call requires a full reasoning cycle, making chains of atomic API calls slow and error-prone. What might be a simple loop in code becomes a complex multi-step reasoning process for an agent, with opportunities for failure at each step.

The problem compounds when massive API specifications are transformed into MCP tools. These comprehensive conversions overwhelm agents with choices, turning them from intelligent assistants into what Lowin calls "obsessive API librarians"—entities more focused on navigating tool specifications than solving user problems. Cryptic parameter names and complex nested structures that make perfect sense for APIs confuse language models trained on natural language. The solution isn't to expose every API endpoint as an MCP tool, but to curate machine-first interfaces specifically designed for agent interaction. Yet most organizations lack the expertise or resources to redesign their APIs from scratch, leaving them stuck between inadequate automation and expensive manual intervention.

### The Context Engineering Imperative

Context engineering has emerged as the critical skill for 2025—the discipline of designing systems that assemble relevant information for LLMs at the right time. Unlike prompt engineering's focus on crafting perfect instructions, context engineering treats the entire context window as a dynamic workspace that must be carefully managed. This shift represents a fundamental change in how we think about AI system design, moving from static prompts to dynamic information orchestration.

Effective context engineering requires sophisticated strategies working in concert. Dynamic selection ensures that only the most relevant tools and data are retrieved for each task. Intelligent compression summarizes historical interactions to prevent context overflow while preserving essential information. Strategic isolation splits complex problems across specialized contexts, preventing interference between unrelated concerns. Format optimization uses token-efficient structures, with YAML requiring 66% fewer tokens than JSON for the same information. Yet most MCP servers operate with static tool sets and no context management capabilities, leaving agents to drown in irrelevant information while missing critical details.

## The Failure Landscape

### Production Horror Stories

The transition from development to production has revealed catastrophic failure modes that weren't anticipated in controlled environments. Microsoft's AI Red Team and industry researchers have catalogued numerous incidents that serve as cautionary tales. In July 2025, Replit experienced a nightmare scenario when an AI agent deleted over 1,200 production records despite explicit "code freeze" instructions meant to prevent any changes. The agent had correctly understood it shouldn't modify code but failed to extend that restriction to data operations.

Security researchers from Knostic scanned nearly 2,000 MCP servers exposed to the internet, finding that all verified servers lacked any form of authentication. This essentially meant anyone could access internal tool listings and potentially exfiltrate sensitive data. Memory poisoning attacks have emerged as a particularly insidious threat, where malicious instructions stored in agent memory are later executed without validation, turning helpful assistants into security vulnerabilities. Multi-agent systems face their own unique challenges, with small errors in one agent cascading through workflows to cause system-wide breakdowns, much like a game of telephone gone catastrophically wrong.

### Common Failure Patterns

Our research has identified recurring patterns that transcend specific implementations or use cases. Agents regularly skip preconditions, attempting actions without checking prerequisites—posting to social media without authentication, trying to refuel vehicles without checking capacity, or modifying records without verifying permissions. These aren't random errors but systematic failures in how agents reason about sequences of operations.

Instruction misinterpretation represents another category where agents follow the letter but not the spirit of instructions. An agent told to book a flight "in November" might calculate dates incorrectly and book for January, or one instructed to refuel "before starting a journey" might interpret this as refueling after beginning to drive. Tool calling errors manifest as JSON generation failures, parameter type mismatches, and incorrect argument formatting, particularly acute in smaller or quantized models that struggle with precise syntax generation.

Context fragmentation occurs when agents operate on incomplete information from siloed data sources, making decisions based on partial views that would be obviously wrong with complete information. The black box nature of agent operations compounds these issues, providing no visibility into decision-making processes and making debugging nearly impossible. When an agent fails, teams often can't determine whether it was due to context confusion, instruction misunderstanding, or tool calling errors without extensive log analysis.

## The Middleware Solution

### Why Middleware?

The traditional approach of building perfect MCP servers with all necessary features has proven impractical at scale. Different use cases require different capabilities, and baking everything into servers creates an explosion of complexity that becomes unmaintainable as features accumulate. Rigid implementations with hard-coded behaviors can't adapt to different contexts or user needs. Every enhancement requires modifying server code, slowing innovation to a crawl. Features developed for one server don't transfer to others, leading to duplicated effort and inconsistent experiences across an organization's tool ecosystem.

Middleware offers a fundamentally different philosophy: composition over implementation. Instead of building monolithic servers that try to do everything, we build simple servers that do one thing well and enhance them through composable middleware layers. This approach mirrors successful patterns from web development, where middleware transformed simple HTTP servers into sophisticated application platforms.

### The WAGS Philosophy

WAGS implements a proxy-based middleware architecture that intercepts communication between agents and MCP servers. This positioning enables incremental enhancement where organizations can start simple and add complexity only as needed. Solutions become reusable, with the same middleware applicable to multiple servers regardless of their implementation details. Separation of concerns keeps servers focused on their core functionality while middleware handles cross-cutting concerns like security, logging, and user interaction. Teams can experiment easily, testing new patterns without modifying production servers or risking existing functionality.

The power of this approach becomes clear when considering real-world scenarios. An organization might have dozens of MCP servers from different vendors, open-source projects, and internal teams. Without middleware, adding authentication to all of them would require modifying each server individually—if you even have access to the source code. With WAGS, a single authentication middleware can secure all servers uniformly, with configuration changes rather than code modifications.

### Research-Driven Middleware

Each WAGS middleware component addresses specific, research-validated failure modes we've identified through extensive analysis of production deployments. These aren't theoretical solutions but practical responses to real problems organizations face today.

RootsMiddleware solves the access control problem that security researchers identified in thousands of exposed servers. By implementing URI-based access control at the proxy layer, it ensures agents can only access authorized resources without requiring any modifications to the underlying servers. A GitHub integration might be restricted to specific repositories, or a file system tool limited to certain directories, all configured through simple URI patterns rather than complex code changes.

ElicitationMiddleware enables human-in-the-loop interactions for critical operations. When an agent attempts a dangerous action like deleting records or sending emails, the middleware automatically prompts users for confirmation or parameter review. This addresses the catastrophic failure modes where agents have deleted production data or sent incorrect communications. The beauty lies in its simplicity—server developers don't need to implement complex interaction flows; they just annotate parameters that require human oversight.

Future middleware components, based on ongoing research, will address emerging patterns. Context optimization middleware will dynamically filter available tools based on the current task, reducing context pollution. Semantic caching will reuse previous computations to reduce redundant processing. Error recovery middleware will implement automatic retry logic with exponential backoff for transient failures. Audit logging will provide comprehensive tracking for compliance and debugging, creating the visibility that's currently missing from black box operations.

## The Value Proposition

### For Server Users

Organizations using MCP servers that lack essential features face a common dilemma: accept limitations or switch to different servers. WAGS offers a third path. No modification of existing servers is required; capabilities are added through the proxy layer. Elicitation can be applied immediately to any server's dangerous operations, providing safety without waiting for vendor updates. The same middleware patterns work across all servers, creating a consistent experience regardless of underlying implementations. Adoption can be gradual, starting with one middleware component and expanding as comfort and needs grow.

Consider a company using an open-source database MCP server that lacks audit logging. Rather than forking the project and maintaining a custom version, they can add audit middleware through WAGS. When they later add a cloud storage MCP server, the same audit middleware automatically provides logging there too. The investment in middleware configuration pays dividends across their entire tool ecosystem.

### For Server Developers

Building MCP servers becomes dramatically simpler when developers can focus on core functionality and let middleware handle cross-cutting concerns. Time-to-market improves when teams can ship simple servers and enhance them with middleware based on user needs. Production usage reveals which middleware patterns users actually need, informing future development priorities. Complexity can be added progressively, with built-in features added only when patterns stabilize and prove their value.

A developer creating a new email MCP server doesn't need to implement rate limiting, authentication, audit logging, and parameter validation from day one. They can focus on the core email functionality, ship quickly, and let users add the middleware they need. As patterns emerge—perhaps most users add elicitation for email recipients—these can be incorporated into future versions or remain as middleware options.

### For Organizations

Deploying AI agents in production requires addressing numerous concerns beyond basic functionality. WAGS provides enterprise-ready solutions without enterprise complexity. Risk mitigation happens through uniformly applied security and safety controls. Compliance requirements are met through audit trails and access controls without custom development. Cost optimization occurs through intelligent context management that reduces token usage. The architecture remains future-proof, with new middleware addressing emerging failure modes as they're discovered.

The economic argument is compelling. Rather than spending months building custom safety features into each MCP server, organizations can apply proven middleware patterns in hours. When new vulnerabilities are discovered—as they inevitably will be in this rapidly evolving space—patches can be deployed as middleware updates rather than server modifications.

## The Path Forward

### Embracing Uncertainty

The uncomfortable truth about AI agents and MCP servers is that we're still learning what works. The patterns that seem obvious today may prove problematic tomorrow. Rather than waiting for perfect knowledge that may never come, WAGS provides a framework for iterative improvement. Each failure becomes a learning opportunity, each success a pattern to replicate.

This approach acknowledges that different organizations have different needs. A startup might prioritize speed and flexibility, while a bank requires extensive audit trails and access controls. Academic researchers might need detailed logging for analysis, while production systems optimize for performance. Middleware allows each group to compose exactly the solution they need without forcing their requirements on others.

### Community-Driven Evolution

The open nature of the middleware pattern enables rapid community-driven evolution. When someone discovers a new failure mode and develops a solution, that innovation immediately benefits everyone using compatible systems. A discovery about context management or error handling isn't locked inside a proprietary server but becomes a reusable component that raises the bar for the entire ecosystem.

This collaborative approach has proven successful in other domains. The web development community has created thousands of middleware components for Express.js, each solving specific problems. We envision a similar ecosystem for MCP, where specialized middleware addresses everything from authentication to monitoring to domain-specific requirements.

### Toward Intelligent Orchestration

The future of MCP extends beyond better servers to intelligent orchestration layers that adapt to agent capabilities, with different models receiving different support based on their strengths and weaknesses. These systems will learn from interactions, with patterns emerging from actual usage rather than theoretical models. Optimization will happen automatically, with context management improving over time based on observed performance. Scaling will be graceful, from single-server deployments to complex multi-server orchestrations.

Imagine middleware that detects when an agent is struggling with context overload and automatically switches to a more focused tool set. Or middleware that learns which parameter combinations frequently require human review and proactively suggests elicitation. These capabilities aren't science fiction—they're natural extensions of the middleware pattern combined with modern machine learning techniques.

## Conclusion

WAGS represents a fundamental shift in how we approach MCP server development and deployment. Instead of pursuing perfect, monolithic implementations that try to anticipate every need, we embrace a world of simple servers enhanced by intelligent middleware. This approach acknowledges the reality that we're still discovering what makes AI agents effective while providing practical tools to address today's known challenges.

The middleware pattern transcends temporary fixes or workarounds. It recognizes that the interface between AI agents and external systems requires a flexible, evolvable layer that can adapt as our understanding deepens. By separating concerns and enabling composition, WAGS ensures that innovations in handling context rot, improving safety, and optimizing performance can be immediately applied across the entire ecosystem without waiting for every server to implement them independently.

As we navigate this new frontier of AI-powered automation, WAGS provides both a safety net for today's deployments and a platform for tomorrow's innovations. Organizations can deploy AI agents with confidence, knowing they have tools to address both known and unknown challenges. Developers can build focused, high-quality servers without the burden of implementing every conceivable feature. Users benefit from consistent experiences and improving capabilities without constant server replacements.

The question isn't whether your MCP servers are perfect—it's whether you have the tools to make them better. With WAGS, the answer is always yes. The journey toward effective AI agents is just beginning, and WAGS ensures you're equipped for whatever comes next.
