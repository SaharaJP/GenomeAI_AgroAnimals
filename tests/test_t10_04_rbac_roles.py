from web_cabinet import rbac


def test_roles_permissions_personalization_matrix():
    viewer = set(rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_VIEWER])
    operator = set(rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_OPERATOR])
    director = set(rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_DIRECTOR])
    zootech = set(rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_ZOOTECH])
    vet = set(rbac.DEFAULT_ROLE_PERMISSIONS[rbac.ROLE_VET])

    # Saved views + favorites are available to all roles (at least view+write for own)
    for perms in (viewer, operator, director, zootech, vet):
        assert rbac.PERM_SAVED_VIEWS_VIEW in perms
        assert rbac.PERM_SAVED_VIEWS_WRITE in perms
        assert rbac.PERM_FAVORITES_VIEW in perms
        assert rbac.PERM_FAVORITES_WRITE in perms

    # Report templates
    assert rbac.PERM_TEMPLATES_VIEW not in viewer
    assert rbac.PERM_TEMPLATES_WRITE not in viewer
    assert rbac.PERM_TEMPLATES_GENERATE not in viewer

    assert rbac.PERM_TEMPLATES_VIEW in operator
    assert rbac.PERM_TEMPLATES_WRITE not in operator
    assert rbac.PERM_TEMPLATES_GENERATE not in operator

    for perms in (director, zootech, vet):
        assert rbac.PERM_TEMPLATES_VIEW in perms
        assert rbac.PERM_TEMPLATES_WRITE in perms
        assert rbac.PERM_TEMPLATES_GENERATE in perms
