import os
from pathlib import Path

import pandas as pd
import pytest

from genomeai.target.validators_v2 import load_fixture_folder, validate_target_v2_relations

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "target_v2"

def test_target_v2_fixtures_loadable():
    dfs = load_fixture_folder(str(FIXTURES_DIR))
    # ensure we have at least core tables
    assert "dm_farms" in dfs
    assert "dm_animals" in dfs
    assert "dm_lactations" in dfs

def test_target_v2_relations_no_errors():
    dfs = load_fixture_folder(str(FIXTURES_DIR))
    issues = validate_target_v2_relations(dfs)
    errors = [i for i in issues if i.severity == "ERROR"]
    assert errors == [], f"Found ERROR issues: {errors}"
