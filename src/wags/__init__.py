"""WAGS - Web Agent Gateway System."""

from importlib.metadata import version

from wags.proxy import create_proxy
from wags.utils.config import load_config

__version__ = version("wags")

__all__ = [
    "create_proxy",
    "load_config",
    "__version__",
]