from __future__ import annotations

from streamlit_app.personalization import required_permission_for_favorite, can_open_favorite
from web_cabinet import rbac


def test_required_permission_for_favorites_mapping() -> None:
    assert required_permission_for_favorite("alert") == rbac.PERM_ALERTS_VIEW
    assert required_permission_for_favorite("report") == rbac.PERM_EXPORT_DOWNLOAD
    assert required_permission_for_favorite("dashboard_report") == rbac.PERM_EXPORT_DOWNLOAD
    assert required_permission_for_favorite("group") == rbac.PERM_DRILLDOWN_VIEW
    assert required_permission_for_favorite("pen") == rbac.PERM_DRILLDOWN_VIEW
    assert required_permission_for_favorite("animal") == rbac.PERM_DRILLDOWN_VIEW
    assert required_permission_for_favorite("cow") == rbac.PERM_DRILLDOWN_VIEW
    assert required_permission_for_favorite("unknown") is None


def test_can_open_favorite_respects_permissions() -> None:
    assert can_open_favorite(object_type="alert", permissions=set()) is False
    assert can_open_favorite(object_type="alert", permissions={rbac.PERM_ALERTS_VIEW}) is True
    assert can_open_favorite(object_type="report", permissions={rbac.PERM_EXPORT_DOWNLOAD}) is True
    assert can_open_favorite(object_type="group", permissions={rbac.PERM_DRILLDOWN_VIEW}) is True
    assert can_open_favorite(object_type="group", permissions={rbac.PERM_KPI_VIEW}) is False
