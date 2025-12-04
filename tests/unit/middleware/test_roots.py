"""Unit tests for RootsMiddleware."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams, Root
from pydantic.networks import AnyUrl

from wags.middleware.roots import RootsMiddleware, requires_root


class TestRequiresRootDecorator:
    """Test the @requires_root decorator behavior."""

    def test_decorator_validates_template_variables(self) -> None:
        """Test that @requires_root validates template variables against function parameters."""

        # Valid: all template variables are function parameters
        @requires_root("https://github.com/{owner}/{repo}")
        def valid_func(owner: str, repo: str, title: str) -> None:
            pass

        assert getattr(valid_func, "__root_template__") == "https://github.com/{owner}/{repo}"

        # Invalid: template variable 'repo' not in function parameters
        with pytest.raises(NameError, match="Template variable.*{'repo'}.*not found"):

            @requires_root("https://github.com/{owner}/{repo}")
            def invalid_func(owner: str, title: str) -> None:
                pass

        # Invalid: multiple missing variables
        with pytest.raises(NameError, match="Template variable.*not found"):

            @requires_root("https://api.com/{user}/{project}/{version}")
            def missing_params(user: str) -> None:
                pass

        # Valid: no template variables
        @requires_root("https://github.com/static/path")
        def no_vars() -> None:
            pass

        assert getattr(no_vars, "__root_template__") == "https://github.com/static/path"

    def test_decorator_prevents_duplicate_different_template(self) -> None:
        """Test that decorator raises error for different templates."""

        @requires_root("https://github.com/{owner}/{repo}")
        def method(owner: str, repo: str) -> None:
            pass

        # Applying different template should raise
        with pytest.raises(ValueError) as exc_info:
            requires_root("https://api.example.com/{endpoint}")(method)

        assert "already has root template" in str(exc_info.value)
        assert "https://github.com/{owner}/{repo}" in str(exc_info.value)

    def test_decorator_allows_same_template_idempotent(self) -> None:
        """Test that decorator is idempotent for same template."""

        @requires_root("https://github.com/{owner}/{repo}")
        def method(owner: str, repo: str) -> None:
            pass

        # Applying same template should be fine (idempotent)
        decorated_again = requires_root("https://github.com/{owner}/{repo}")(method)
        assert decorated_again is method  # Should return same function
        assert getattr(method, "__root_template__") == "https://github.com/{owner}/{repo}"

    def test_decorator_sets_template_attribute(self) -> None:
        """Test that decorator sets the __root_template__ attribute."""
        template = "https://api.example.com/{version}/{endpoint}"

        @requires_root(template)
        def method(version: str, endpoint: str) -> None:
            pass

        assert hasattr(method, "__root_template__")
        assert getattr(method, "__root_template__") == template


class MockHandlers:
    """Mock handlers with decorated methods."""

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(self, owner: str, repo: str, title: str) -> None:
        pass

    @requires_root("https://github.com/{owner}/{repo}/pulls/{pr}")
    async def review_pr(self, owner: str, repo: str, pr: int) -> None:
        pass

    async def undecorated_method(self) -> None:
        pass


@pytest.fixture
def handlers() -> Any:
    """Provide mock handlers instance."""
    return MockHandlers()


@pytest.fixture
def middleware(handlers: Any) -> Any:
    """Provide middleware instance with handlers."""
    return RootsMiddleware(handlers=handlers)


def create_context_with_roots(arguments: dict[str, Any], roots: list[str] | None = None) -> MiddlewareContext[Any]:
    """Create a middleware context with given arguments and roots."""
    message = CallToolRequestParams(name="test_method", arguments=arguments)

    # Mock FastMCP context with roots if provided
    fastmcp_context = None
    if roots is not None:
        mock_fastmcp_context = MagicMock()
        # list_roots should return the list of Root objects directly
        mock_list_roots = AsyncMock(
            return_value=[Root(uri=AnyUrl(url), name=f"root_{i}") for i, url in enumerate(roots)]
        )
        mock_fastmcp_context.list_roots = mock_list_roots
        fastmcp_context = mock_fastmcp_context

    # Create context with fastmcp_context in constructor
    context = MiddlewareContext(message=message, fastmcp_context=fastmcp_context)
    return context


@pytest.mark.asyncio
async def test_literal_root_matching(middleware: Any, handlers: Any) -> None:
    """Test simple prefix matching for literal roots."""
    # Should allow myorg repos
    context = create_context_with_roots({"owner": "myorg", "repo": "test-repo"}, roots=["https://github.com/myorg/"])
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context  # Passes through

    # Should deny other orgs
    context = create_context_with_roots({"owner": "other-org", "repo": "test"}, roots=["https://github.com/myorg/"])
    with pytest.raises(PermissionError, match="Access denied"):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_concrete_prefix_matching(middleware: Any, handlers: Any) -> None:
    """Test that roots work as concrete prefixes only."""
    # Should match any repo in myorg
    context = create_context_with_roots({"owner": "myorg", "repo": "any-repo"}, roots=["https://github.com/myorg/"])
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context

    # Should NOT match other orgs
    context = create_context_with_roots({"owner": "other-org", "repo": "test"}, roots=["https://github.com/myorg/"])
    with pytest.raises(PermissionError):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_empty_roots_denies_all(middleware: Any, handlers: Any) -> None:
    """Test that empty roots list denies all access."""
    context = create_context_with_roots({"owner": "any", "repo": "repo"}, roots=[])
    with pytest.raises(PermissionError, match="No roots configured"):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_missing_parameter(middleware: Any, handlers: Any) -> None:
    """Test clear error for missing template params."""
    # Missing 'repo' parameter
    context = create_context_with_roots({"owner": "myorg"}, roots=["https://github.com/myorg/"])
    with pytest.raises(ValueError, match="Missing required parameter 'repo'"):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_undecorated_method_passes(middleware: Any, handlers: Any) -> None:
    """Test that undecorated methods bypass validation."""
    # Even with no roots, undecorated methods pass
    context = create_context_with_roots({}, roots=[])
    result = await middleware.handle_on_tool_call(context, handlers.undecorated_method)
    assert result == context  # Passes through without validation


@pytest.mark.asyncio
async def test_multiple_concrete_roots(middleware: Any, handlers: Any) -> None:
    """Test multiple concrete prefix roots."""
    roots = [
        "https://github.com/trusted/",  # Prefix for trusted org
        "https://github.com/partner/",  # Prefix for partner org
    ]

    # Should match trusted prefix
    context = create_context_with_roots({"owner": "trusted", "repo": "any-repo"}, roots=roots)
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context

    # Should match partner prefix
    context = create_context_with_roots({"owner": "partner", "repo": "specific-repo"}, roots=roots)
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context

    # Should deny others
    context = create_context_with_roots({"owner": "untrusted", "repo": "repo"}, roots=roots)
    with pytest.raises(PermissionError):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_specific_repo_root(middleware: Any, handlers: Any) -> None:
    """Test matching a specific repository."""
    roots = ["https://github.com/myorg/specific-repo"]

    # Should match exact repo
    context = create_context_with_roots({"owner": "myorg", "repo": "specific-repo"}, roots=roots)
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context

    # Should also match sub-resources of that repo
    context = create_context_with_roots({"owner": "myorg", "repo": "specific-repo", "pr": 123}, roots=roots)
    result = await middleware.handle_on_tool_call(context, handlers.review_pr)
    assert result == context

    # Should deny other repos in same org
    context = create_context_with_roots({"owner": "myorg", "repo": "other-repo"}, roots=roots)
    with pytest.raises(PermissionError):
        await middleware.handle_on_tool_call(context, handlers.create_issue)


@pytest.mark.asyncio
async def test_prefix_allows_sub_resources(middleware: Any, handlers: Any) -> None:
    """Test that prefix roots allow access to sub-resources."""
    # Should match sub-resource (PR review) under allowed repo
    context = create_context_with_roots(
        {"owner": "myorg", "repo": "myrepo", "pr": 42}, roots=["https://github.com/myorg/myrepo"]
    )
    result = await middleware.handle_on_tool_call(context, handlers.review_pr)
    assert result == context  # Prefix matches the expanded template


@pytest.mark.asyncio
async def test_no_roots_capability_skips_validation(middleware: Any, handlers: Any) -> None:
    """Test that clients without roots capability skip validation entirely."""
    # Create context without roots capability
    message = CallToolRequestParams(name="test_method", arguments={"owner": "any", "repo": "repo"})

    # Mock a context with no roots capability
    mock_fastmcp_context = MagicMock()
    mock_session = MagicMock()
    mock_client_params = MagicMock()
    mock_capabilities = MagicMock()
    mock_capabilities.roots = None  # No roots capability

    mock_client_params.capabilities = mock_capabilities
    mock_session.client_params = mock_client_params
    mock_fastmcp_context.session = mock_session

    context = MiddlewareContext(message=message, fastmcp_context=mock_fastmcp_context)

    # Should pass through without validation
    result = await middleware.handle_on_tool_call(context, handlers.create_issue)
    assert result == context  # Passes through without any permission check
