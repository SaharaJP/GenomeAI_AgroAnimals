from __future__ import annotations

import warnings


def warn_legacy_import(*, legacy_path: str, new_path: str) -> None:
    warnings.warn(
        f"{legacy_path} is deprecated; import from {new_path} instead.",
        DeprecationWarning,
        stacklevel=2,
    )


__all__ = ["warn_legacy_import"]
