from pathlib import Path

from streamlit_app.ia_v3 import load_ia_config, build_nav_for_user
from web_cabinet import rbac


def _flat(groups):
    return {it.key: it for g in groups for it in g.items}


def test_home_page_resolves_per_role():
    cfg = load_ia_config(Path("configs/ui/ia_v3.yaml"))

    for role in [
        rbac.ROLE_DIRECTOR,
        rbac.ROLE_ZOOTECH,
        rbac.ROLE_VET,
        rbac.ROLE_OPERATOR,
        rbac.ROLE_ADMIN,
        rbac.ROLE_VIEWER,
    ]:
        perms = set(rbac.ROLE_PERMISSIONS.get(role, []))
        groups = build_nav_for_user(cfg=cfg, role=role, permissions=perms)
        flat = _flat(groups)
        assert "home" in flat
        page = flat["home"].page
        assert page.endswith(f"0_Home_{role}.py")
