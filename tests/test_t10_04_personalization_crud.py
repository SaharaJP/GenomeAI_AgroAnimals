import sqlite3

from web_cabinet.db import init_db
from web_cabinet import rbac

from web_cabinet.saved_views import create_saved_view, list_saved_views, get_saved_view, delete_saved_view
from web_cabinet.report_templates import create_template, list_templates, get_template, update_template, delete_template
from web_cabinet.favorites import add_favorite, is_favorite, list_favorites, remove_favorite


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_rbac_has_new_permissions():
    assert rbac.PERM_SAVED_VIEWS_VIEW in rbac.ALL_PERMISSIONS
    assert rbac.PERM_SAVED_VIEWS_WRITE in rbac.ALL_PERMISSIONS
    assert rbac.PERM_TEMPLATES_VIEW in rbac.ALL_PERMISSIONS
    assert rbac.PERM_TEMPLATES_WRITE in rbac.ALL_PERMISSIONS
    assert rbac.PERM_TEMPLATES_GENERATE in rbac.ALL_PERMISSIONS
    assert rbac.PERM_FAVORITES_VIEW in rbac.ALL_PERMISSIONS
    assert rbac.PERM_FAVORITES_WRITE in rbac.ALL_PERMISSIONS


def test_saved_views_crud_user_and_shared():
    conn = _conn()
    tenant_id = "t1"
    create_saved_view(
        conn,
        view_id="v1",
        tenant_id=tenant_id,
        created_by=1,
        created_by_username="u1",
        scope="user",
        name="My view",
        page_key="kpi_drilldown",
        state={"kpi_drilldown.kpi_id": "milk_total_kg_7d"},
        data_version="dv_demo",
    )
    create_saved_view(
        conn,
        view_id="v2",
        tenant_id=tenant_id,
        created_by=2,
        created_by_username="u2",
        scope="shared",
        name="Shared",
        page_key="kpi_drilldown",
        state={"kpi_drilldown.kpi_id": "SCC_mean_7d"},
    )

    views_u1 = list_saved_views(conn, tenant_id=tenant_id, user_id=1, page_key="kpi_drilldown", include_shared=True)
    ids = {v["view_id"] for v in views_u1}
    assert ids == {"v1", "v2"}

    views_u2_only = list_saved_views(conn, tenant_id=tenant_id, user_id=2, page_key="kpi_drilldown", include_shared=False)
    assert {v["view_id"] for v in views_u2_only} == {"v2"}

    v1 = get_saved_view(conn, tenant_id=tenant_id, view_id="v1")
    assert v1 and v1["state"]["kpi_drilldown.kpi_id"] == "milk_total_kg_7d"

    delete_saved_view(conn, tenant_id=tenant_id, view_id="v1")
    assert get_saved_view(conn, tenant_id=tenant_id, view_id="v1") is None


def test_report_templates_crud():
    conn = _conn()
    tenant_id = "t1"
    t = create_template(
        conn,
        template_id="t1",
        tenant_id=tenant_id,
        created_by=1,
        created_by_username="u1",
        scope="user",
        name="Tpl",
        sections=["kpi_summary"],
        metrics=["milk_total_kg_7d"],
        options={"role": "director"},
    )
    assert t["template_id"] == "t1"

    out = list_templates(conn, tenant_id=tenant_id, user_id=1, include_shared=True)
    assert len(out) == 1

    update_template(conn, tenant_id=tenant_id, template_id="t1", name="Tpl2", sections=["alerts"], metrics=["SCC_mean_7d"])
    got = get_template(conn, tenant_id=tenant_id, template_id="t1")
    assert got and got["name"] == "Tpl2"
    assert got["sections"] == ["alerts"]

    delete_template(conn, tenant_id=tenant_id, template_id="t1")
    assert get_template(conn, tenant_id=tenant_id, template_id="t1") is None


def test_favorites_add_remove_idempotent():
    conn = _conn()
    tenant_id = "t1"
    add_favorite(conn, tenant_id=tenant_id, user_id=1, object_type="animal", object_id="A1", label="Animal A1")
    add_favorite(conn, tenant_id=tenant_id, user_id=1, object_type="animal", object_id="A1", label="Animal A1")
    assert is_favorite(conn, tenant_id=tenant_id, user_id=1, object_type="animal", object_id="A1") is True
    favs = list_favorites(conn, tenant_id=tenant_id, user_id=1)
    assert len(favs) == 1
    remove_favorite(conn, tenant_id=tenant_id, user_id=1, object_type="animal", object_id="A1")
    assert is_favorite(conn, tenant_id=tenant_id, user_id=1, object_type="animal", object_id="A1") is False
