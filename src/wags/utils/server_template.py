"""Server template utilities for creating new WAGS servers."""

from pathlib import Path

from fastmcp.utilities.logging import get_logger
from jinja2 import Template

logger = get_logger("wags.utils.server_template")


def create_server_scaffold(name: str, path: Path | None = None) -> None:
    """Create a new server scaffold with handlers template.

    Note: This does NOT create a config.json - users should provide their own.
    """
    if path is None:
        path = Path("servers") / name

    path.mkdir(parents=True, exist_ok=True)

    class_name = name.replace("-", "_").title() + "Handlers"
    templates_dir = Path(__file__).parent.parent / "templates"

    with open(templates_dir / "main.py.j2") as f:
        main_template = Template(f.read())
    main_content = main_template.render(name=name, class_name=class_name)
    (path / "main.py").write_text(main_content)

    with open(templates_dir / "handlers.py.j2") as f:
        handlers_template = Template(f.read())
    handlers_content = handlers_template.render(name=name, class_name=class_name)
    (path / "handlers.py").write_text(handlers_content)

    (path / "__init__.py").write_text("")

    logger.info(f"Created server scaffold at {path}")
    logger.info("Note: You need to create your own config.json with mcpServers configuration")
