"""TDD: analytics performance indexes must exist after migration 20260504_11."""
from __future__ import annotations

import os

import pytest

try:
    from sqlalchemy import create_engine, text as sa_text
    _SA_AVAILABLE = True
except ImportError:
    _SA_AVAILABLE = False

_DSN_RAW = os.environ.get("GENOMEAI_RUNTIME_POSTGRES_DSN", "")
# sqlalchemy requires postgresql+psycopg2:// or postgresql+psycopg:// prefix
_DSN = _DSN_RAW.replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1) if _DSN_RAW else ""

_SKIP = not (_SA_AVAILABLE and _DSN)
_SKIP_REASON = (
    "sqlalchemy not available" if not _SA_AVAILABLE
    else "GENOMEAI_RUNTIME_POSTGRES_DSN not set"
)

# The 6 indexes the migration must create.
REQUIRED_INDEXES = [
    ("dm_milkings_daily", "idx_milkings_tenant_date"),
    ("dm_milkings_daily", "idx_milkings_animal_date"),
    ("dm_health_events",  "idx_health_tenant_date"),
    ("dm_health_events",  "idx_health_animal_date"),
    ("dm_repro_events",   "idx_repro_tenant_date"),
    ("dm_sensors_daily",  "idx_sensors_animal_date"),
]


@pytest.fixture(scope="module")
def pg_engine():
    if _SKIP:
        pytest.skip(_SKIP_REASON)
    engine = create_engine(_DSN, future=True)
    yield engine
    engine.dispose()


def _existing_indexes(engine) -> set[tuple[str, str]]:
    tables = [t for t, _ in REQUIRED_INDEXES]
    with engine.connect() as conn:
        rows = conn.execute(
            sa_text(
                "SELECT tablename, indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "  AND tablename = ANY(:tables)"
            ),
            {"tables": tables},
        ).fetchall()
    return {(r[0], r[1]) for r in rows}


@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
class TestAnalyticsIndexesExist:
    """After migration 20260504_11, all six analytics indexes must be present."""

    def test_milkings_tenant_date_index_exists(self, pg_engine) -> None:
        assert ("dm_milkings_daily", "idx_milkings_tenant_date") in _existing_indexes(pg_engine), (
            "Missing idx_milkings_tenant_date on dm_milkings_daily(tenant_id, date). "
            "Apply migration 20260504_11_analytics_indexes."
        )

    def test_milkings_animal_date_index_exists(self, pg_engine) -> None:
        assert ("dm_milkings_daily", "idx_milkings_animal_date") in _existing_indexes(pg_engine), (
            "Missing idx_milkings_animal_date on dm_milkings_daily(animal_id, date)."
        )

    def test_health_tenant_date_index_exists(self, pg_engine) -> None:
        assert ("dm_health_events", "idx_health_tenant_date") in _existing_indexes(pg_engine), (
            "Missing idx_health_tenant_date on dm_health_events(tenant_id, event_date)."
        )

    def test_health_animal_date_index_exists(self, pg_engine) -> None:
        assert ("dm_health_events", "idx_health_animal_date") in _existing_indexes(pg_engine), (
            "Missing idx_health_animal_date on dm_health_events(animal_id, event_date)."
        )

    def test_repro_tenant_date_index_exists(self, pg_engine) -> None:
        assert ("dm_repro_events", "idx_repro_tenant_date") in _existing_indexes(pg_engine), (
            "Missing idx_repro_tenant_date on dm_repro_events(tenant_id, event_date)."
        )

    def test_sensors_animal_date_index_exists(self, pg_engine) -> None:
        assert ("dm_sensors_daily", "idx_sensors_animal_date") in _existing_indexes(pg_engine), (
            "Missing idx_sensors_animal_date on dm_sensors_daily(animal_id, date)."
        )
