# WAGS - Web Agent Gateway System

A Python package for building web agent gateway systems.

## Installation

```bash
uv pip install -e .
```

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run linters
ruff check .
ruff format .
mypy src/

# Build documentation
mkdocs serve
```
