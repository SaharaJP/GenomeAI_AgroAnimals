from __future__ import annotations

"""Entity helpers (Target).

T10-03: Drill-down 3.0

We maintain backward compatibility between slightly different naming conventions
for the same business entities across producers and iterations.

Example:
  - some producers emit object_type="pen" (technical), while UI uses "group".

This module provides:
  - normalize_object_type(): map aliases to canonical values
  - expand_object_types(): return canonical + known aliases for querying
"""

from typing import Optional


def normalize_object_type(t: Optional[str]) -> Optional[str]:
    """Normalize object_type into canonical values.

    Canonical:
      - "animal"
      - "group" (alias: "pen")

    Unknown values are lowercased and returned as-is.
    """

    if t is None:
        return None
    s = str(t).strip()
    if not s:
        return None
    s_low = s.lower()
    if s_low in {"animal", "cow", "cattle"}:
        return "animal"
    if s_low in {"group", "pen", "barn", "lot"}:
        return "group"
    if s_low in {"farm"}:
        return "farm"
    if s_low in {"site", "platform"}:
        return "site"
    return s_low


def expand_object_types(t: Optional[str]) -> list[str]:
    """Return a list of object_type values to query for a given entity.

    Includes canonical and known aliases.
    """

    norm = normalize_object_type(t)
    if not norm:
        return []
    if norm == "animal":
        return ["animal", "cow"]
    if norm == "group":
        return ["group", "pen"]
    return [norm]
