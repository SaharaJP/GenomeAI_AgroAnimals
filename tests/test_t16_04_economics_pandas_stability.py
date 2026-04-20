from __future__ import annotations

import hashlib
import warnings
from pathlib import Path

import pandas as pd

from genomeai.economics_v2 import _assign_float_where, _concat_legacy_compatible, run_economics_v2


EXPECTED_DAILY_SHA256 = "6707f79c6b151ee2def4546e93b3b592550891e718016a21530a80ef0b4933d0"
EXPECTED_MONTHLY_SHA256 = "fde0b27447d49d29bb1ecb6c1669b72075dde3c8cfd7b8b9e2e494adb0247ce9"


def _stable_df_hash(df: pd.DataFrame) -> str:
    ordered = df.sort_values(list(df.columns.astype(str))).reset_index(drop=True)
    payload = ordered.fillna("<NA>").to_csv(index=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_t16_04_run_economics_is_warning_free_and_output_hash_stable(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = run_economics_v2(
            artifacts_root=artifacts,
            data_version="dv_t16_04",
            date_from="2025-01-10",
            date_to="2025-01-10",
            cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
            input_dir=fixtures,
            tenant_id="default",
        )

    assert res.get("ok") is True
    econ_run = str(res.get("economics_run"))
    run_dir = artifacts / "dv_t16_04" / "economics_v2" / econ_run
    daily = pd.read_csv(run_dir / "economics_daily.csv")
    monthly = pd.read_csv(run_dir / "economics_monthly.csv")

    econ_future_warnings = [
        w for w in caught
        if issubclass(w.category, FutureWarning) and "economics_v2.py" in str(getattr(w, "filename", ""))
    ]
    assert econ_future_warnings == []

    assert _stable_df_hash(daily) == EXPECTED_DAILY_SHA256
    assert _stable_df_hash(monthly) == EXPECTED_MONTHLY_SHA256


def test_t16_04_assign_float_where_handles_empty_mask_without_dtype_warning() -> None:
    df = pd.DataFrame({"milk_price_rub_per_kg": [50.0, 52.0]})
    mask = pd.Series([False, False], index=df.index)
    override = pd.Series([], dtype="float64")

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=FutureWarning)
        _assign_float_where(df=df, column="milk_price_rub_per_kg", mask=mask, values=override)

    assert str(df["milk_price_rub_per_kg"].dtype) == "float64"
    assert df["milk_price_rub_per_kg"].tolist() == [50.0, 52.0]


def test_t16_04_concat_normalization_preserves_rows_and_avoids_all_na_concat_warning() -> None:
    pen = pd.DataFrame(
        {
            "level": ["pen"],
            "pen_id": ["PEN_01"],
            "revenue_total_rub": [100.0],
            "pen_name": ["Pen 1"],
        }
    )
    site = pd.DataFrame(
        {
            "level": ["site"],
            "pen_id": [pd.NA],
            "revenue_total_rub": [100.0],
            "pen_name": [pd.NA],
        }
    )
    farm = pd.DataFrame(
        {
            "level": ["farm"],
            "pen_id": [pd.NA],
            "revenue_total_rub": [100.0],
            "pen_name": [pd.NA],
        }
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=FutureWarning)
        out = _concat_legacy_compatible([pen, site, farm])

    assert out["level"].tolist() == ["pen", "site", "farm"]
    assert out["revenue_total_rub"].tolist() == [100.0, 100.0, 100.0]
    assert out.loc[out["level"] == "pen", "pen_name"].iloc[0] == "Pen 1"
    assert out.loc[out["level"] == "site", "pen_name"].isna().all()
