from __future__ import annotations

from pathlib import Path

import pytest


def test_alerts_v2_catalog_has_min_types():
    from genomeai.alerts_v2 import validate_catalog_min_types

    validate_catalog_min_types(Path("configs/alerts_v2/catalog.yaml"), min_types=40)
