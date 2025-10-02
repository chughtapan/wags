# Test Organization

This directory contains all tests for the WAGS framework, organized by test type and scope.

## Test Structure

### 1. Unit Tests (`unit/`)
Tests for individual components in isolation without external dependencies.

**Characteristics:**
- Fast execution (no LLM calls, no network)
- Mock external dependencies
- Test single functions/classes
- No API keys required

**Examples:**
- `unit/middleware/test_roots.py` - RootsMiddleware path validation
- `unit/utils/test_config.py` - Configuration parsing
- `unit/middleware/test_todo.py` - TodoServer state management

**Run:**
```bash
.venv/bin/pytest tests/unit/ -v
```

### 2. Integration Tests (`integration/`)
Tests for interactions between multiple components.

**Characteristics:**
- Test component integration
- May use Client patterns or mock servers
- No real LLM calls (use mocks or test doubles)
- Faster than e2e, slower than unit

**Examples:**
- `integration/test_middleware_integration.py` - Middleware chain interactions
- `integration/test_roots_middleware.py` - RootsMiddleware with real servers

**Run:**
```bash
.venv/bin/pytest tests/integration/ -v
```

### 3. End-to-End Tests (`e2e/`)
Tests with real LLMs using FastAgent patterns.

**Characteristics:**
- **Requires API keys** (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
- Uses real LLM calls via fast-agent
- Tests complete workflows
- Slower execution, costs money
- Use `@pytest.mark.verified_models()` marker

**Examples:**
- `e2e/todos/test_todo.py` - TodoServer workflow with LLM
- `e2e/test_github_server.py` - GitHub server integration

**Run:**
```bash
# With verified models
.venv/bin/pytest tests/e2e/ -v --model gpt-4o
.venv/bin/pytest tests/e2e/ -v --model gpt-4.1

# With other models (may show xfail)
.venv/bin/pytest tests/e2e/ -v --model gpt-4o-mini
```

### 4. Benchmark Tests (`benchmarks/`)
BFCL (Berkeley Function Call Leaderboard) evaluation tests.

**Characteristics:**
- Large-scale evaluation suites
- Excluded from default test runs
- Requires explicit path to run
- Uses `--validate-only` mode for re-validation

**Examples:**
- `benchmarks/bfcl/test_bfcl.py` - BFCL multi-turn tests

**Run:**
```bash
# Run all BFCL tests
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --model gpt-4o

# Run specific category
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py -k "multi_turn_base"

# Validate existing logs
.venv/bin/pytest tests/benchmarks/bfcl/test_bfcl.py --validate-only
```

### 5. Smoke Tests (`smoke/`)
Quick validation and initial experimentation.

**Characteristics:**
- Fast sanity checks
- Initial feature validation
- May not be comprehensive
- Used for rapid development feedback

**Run:**
```bash
.venv/bin/pytest tests/smoke/ -v
```

## Test Patterns

### Using `@pytest.mark.verified_models()`

Mark tests that are only verified to work with specific models:

```python
import pytest

@pytest.mark.verified_models(["gpt-4o", "gpt-4.1"])
async def test_advanced_feature(fast_agent, model):
    """Test runs for all models, but only verified models must pass."""
    # Test implementation
```

**Behavior:**
1. Test runs for all models specified via `--model` flag
2. If test **passes** → always passes (even for unverified models)
3. If test **fails** with verified model → hard failure (must fix)
4. If test **fails** with unverified model → xfail (expected, okay)

**Benefits:**
- Discover when new models work without breaking CI
- Only require known-good models to pass
- Automatically track model compatibility

### FastAgent Patterns

E2E tests use FastAgent for LLM interaction:

```python
@pytest.fixture
def fast_agent(request):
    """Create FastAgent with config from test directory."""
    test_dir = os.path.dirname(__file__)
    config_file = os.path.join(test_dir, "fastagent.config.yaml")

    return FastAgent(
        "Test Agent",
        config_path=config_file,
        ignore_unknown_args=True,
    )

@pytest.mark.asyncio
@pytest.mark.verified_models(["gpt-4o", "gpt-4.1"])
async def test_workflow(fast_agent, model):
    fast = fast_agent

    @fast.agent(
        name="test_agent",
        model=model,
        servers=["my-server"],
        instruction="You are a helpful agent.\n\n{{serverInstructions}}",
    )
    async def test_function():
        async with fast.run() as agent:
            await agent.send("Test prompt")
            # Assertions

    await test_function()
```

### Client Patterns

Integration tests may use Client patterns for direct server interaction:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_with_client():
    server_params = StdioServerParameters(
        command="fastmcp",
        args=["run", "server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Test server interaction
```

## Configuration

### Fixtures (`conftest.py`)

Global fixtures available to all tests:

- `model`: Model name from `--model` CLI option (default: gpt-4o-mini)
- `output_dir`: Output directory from `--output-dir` (default: outputs)
- `fast_agent`: FastAgent instance (e2e tests only)

### Custom Markers

Registered markers:

- `verified_models(models)`: Mark test to only require passing with specified models

### CLI Options

```bash
--model MODEL              # Model to use (default: gpt-4o-mini)
--output-dir DIR          # Output directory (default: outputs)
--validate-only           # Only validate existing logs (benchmarks)
--log-dir DIR             # Log directory for validation
--max-workers N           # Max concurrent tests (default: 4)
```

## Common Commands

```bash
# Run all tests except benchmarks (default)
.venv/bin/pytest tests/

# Run specific test levels
.venv/bin/pytest tests/unit/ -v
.venv/bin/pytest tests/integration/ -v
.venv/bin/pytest tests/e2e/ -v --model gpt-4o

# Run specific test file
.venv/bin/pytest tests/unit/middleware/test_roots.py -v

# Run specific test
.venv/bin/pytest tests/unit/middleware/test_roots.py::test_literal_root_matching -v

# Run with coverage
.venv/bin/pytest tests/unit/ --cov=src/wags --cov-report=html

# Run with different models
.venv/bin/pytest tests/e2e/ --model gpt-4o      # Verified
.venv/bin/pytest tests/e2e/ --model gpt-4.1     # Verified
.venv/bin/pytest tests/e2e/ --model gpt-4o-mini # May xfail
```

## Guidelines

1. **Add tests at the right level:**
   - Logic/algorithms → unit tests
   - Component interaction → integration tests
   - User workflows with LLMs → e2e tests
   - Evaluation suites → benchmarks

2. **Use verified_models for e2e tests:**
   - Always mark e2e tests with known-good models
   - Start with `["gpt-4o", "gpt-4.1"]`
   - Add models as they're verified

3. **Keep tests isolated:**
   - Don't depend on test execution order
   - Clean up state in fixtures
   - Use unique identifiers when needed

4. **Minimize LLM calls:**
   - Prefer unit/integration tests when possible
   - Use mocks for non-essential LLM interactions
   - E2E tests are expensive - make them count
