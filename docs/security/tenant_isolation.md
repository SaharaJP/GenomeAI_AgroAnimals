# Tenant Isolation — Analytics Bridges

## Threat model

GenomeAI runs as a multi-tenant service: multiple farms share one server and one Redis instance.
A request for **farm-A** must never return data belonging to **farm-B**, even if they live in the
same CSV file or DataFrame.

## Scope

The analytics bridges in `web_cabinet/analytics/` are the primary data-access layer between the
web UI and the underlying data sources (CSV / kpi_v2 / alerts_v2).

| Bridge | Public function | Data source |
|---|---|---|
| `sensor_bridge` | `detect_recent_sensor_anomalies(farm_id)` | `dm_milkings_daily.csv` |
| `alerts_bridge` | `list_active_alerts(farm_id)` | `dm_health_events.csv` + generators |
| `kpi_bridge` | `compute_dashboard_kpi(farm_id, as_of)` | `kpi_v2.run_kpi()` DataFrame |

## Design decisions

### 1. Validation before cache

All three public functions raise `ValueError("farm_id must not be empty")` **before** any cache
lookup. This prevents a cached `[]` result (from a prior call with an empty tenant ID) from
silently bypassing the guard.

```
compute_dashboard_kpi("") → raises ValueError immediately
              ↑ validation here
              ↓ cache lookup only after validation passes
_compute_dashboard_kpi_cached(...)
```

### 2. CSV / DataFrame filtering

When a data source has a `tenant_id` or `farm_id` column, the bridge filters to matching rows
before any further processing. The column name lookup tries `tenant_id` first (canonical in demo
data), then `farm_id` for backward compatibility.

```python
# sensor_bridge._from_demo_csv
_tenant_col = next((c for c in ("tenant_id", "farm_id") if c in mk.columns), None)
if _tenant_col:
    mk = mk[mk[_tenant_col] == farm_id]
if mk.empty:
    return []
```

Same pattern applies in `alerts_bridge._alerts_from_health_events`.

For `kpi_bridge`, `_compute_dashboard_kpi_uncached` already filtered at the DataFrame level via
`_get_kpi(df, kpi_id, farm_id)` which uses `df[(df["farm_id"] == farm_id)]`.

### 3. Output stamping

After filtering, every returned dataclass object has `farm_id` set to the requested `farm_id`.
This prevents cross-tenant field confusion at the serialization layer.

### 4. Cache key includes farm_id

The `@cached` decorator builds the Redis cache key from **all function arguments**, including
`farm_id`. Different tenants get different cache slots and cannot read each other's cached results.

Farm-level cache invalidation is also supported: `AnalyticsCache.invalidate_farm(farm_id)` deletes
all keys associated with a farm via a secondary Redis index.

## Verification

Integration tests in `web_cabinet/analytics/tests/test_tenant_isolation.py` cover:

| Test | What it proves |
|---|---|
| `test_sensor_bridge_rejects_empty_farm_id` | Empty `farm_id` raises before any I/O |
| `test_alerts_bridge_rejects_empty_farm_id` | Same for alerts |
| `test_kpi_bridge_rejects_empty_farm_id` | Same for KPI |
| `test_sensor_bridge_farm_a_does_not_leak_farm_b_animals` | A's anomalies contain no B animals |
| `test_sensor_bridge_farm_b_does_not_leak_farm_a_animals` | B's anomalies contain no A animals |
| `test_sensor_bridge_farm_a_has_its_own_anomalies` | Filtering doesn't erase A's own data |
| `test_alerts_bridge_farm_a_does_not_see_farm_b_events` | A's alerts exclude B's health events |
| `test_alerts_bridge_farm_b_sees_its_own_event` | B's alerts include B's health events |
| `test_kpi_bridge_farm_id_in_result_matches_requested_farm` | Result carries the requested `farm_id` |

Fixture setup: two farms (`farm-A`, `farm-B`) both with high-SCC animals in the same CSV.
Without filtering, every query would return all rows. The tests verify that only the correct
tenant's rows appear in the response.

## Generator-sourced alerts

`list_active_alerts` can receive alert dicts from `alerts_v2` generators before falling back to
the CSV path. Generators are called with `canonical_dir` and may return multi-tenant data if the
directory is shared.

`_filter_raw_by_farm_id` is applied to generator output before constructing `ActiveAlert` objects:
- Dicts with `tenant_id` or `farm_id` that don't match the request → dropped.
- Dicts with no tenant field (single-farm/legacy generators) → kept (backward-compatible).

Adding `tenant_id` to generator output is the long-term solution; this filter is a defense-in-depth
layer.

## Known limitations

- **Demo / CSV mode only.** The current bridges fall back to CSV demo data. In production, all
  queries must use parameterized SQL with `WHERE tenant_id = $1`. This will be enforced when the
  Postgres-native bridge is wired in (T34-01/T34-02 cutover).

- **No column → no filter.** If the CSV lacks a `tenant_id` or `farm_id` column, no filtering
  is applied and all rows are returned. Acceptable for single-farm fixtures; must not occur in
  production data.

- **Generator no-tenant-field dicts are kept.** `_filter_raw_by_farm_id` is backward-compatible:
  dicts without tenant fields are not dropped. Once generators are updated to include `tenant_id`,
  the filter will enforce isolation even for dicts where the field is absent.

## Open security issues (backlog)

| ID | Severity | Issue | Owner |
|---|---|---|---|
| SEC-1 | WARNING | `analytics_v1.py` KPI endpoints accept `?farm_id=` param without checking it against the session token's authorized farm scope. Any authenticated user can query any farm's KPI. Fix: enforce `farm_id == user.farm_id` or admin role check. | T34 backend |
| SEC-2 | WARNING | `cache.py:_from_jsonable` uses `importlib.import_module(value["__module__"])` on data read from Redis. If Redis is reachable by an adversary, this is a deserialization code-execution vector. Fix: allowlist known analytics modules (`web_cabinet.analytics.*`). | Cache team |

## Audit trail

Any `farm_id` used in a read operation is available in the cache farm-index
(`genomeai:analytics:farm:{farm_id}` Redis set) for observability. Write-path mutations (if any)
must emit audit events per `docs/production_security_and_iam_baseline.md`.
