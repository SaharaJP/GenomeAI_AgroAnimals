"""Compatibility shim for deprecated ``multipart`` imports.

Starlette/FastAPI releases prior to their python-multipart migration still import
``multipart`` and ``multipart.multipart``. Newer ``python-multipart`` versions
keep that alias but emit ``PendingDeprecationWarning`` on import. This local
shim preserves the old import surface while delegating to ``python_multipart``
without warnings.
"""

from python_multipart import *  # noqa: F401,F403
from python_multipart import __all__ as _python_multipart_all
from python_multipart import __author__, __copyright__, __license__, __version__
from python_multipart.multipart import parse_options_header

__all__ = list(_python_multipart_all) + [
    "parse_options_header",
    "__version__",
    "__author__",
    "__copyright__",
    "__license__",
]
