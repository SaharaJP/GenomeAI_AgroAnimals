from __future__ import annotations

from dataclasses import dataclass

import pytest

from streamlit_app import common as common_mod


class _StopCalled(Exception):
    pass


@dataclass
class _FakeStreamlit:
    last_error: str | None = None

    def error(self, message: str) -> None:
        self.last_error = message

    def stop(self) -> None:
        raise _StopCalled()


def test_t15_10_streamlit_require_permissions_uses_core_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStreamlit()
    monkeypatch.setattr(common_mod, "st", fake)
    with pytest.raises(_StopCalled):
        common_mod.require_permissions({"role": "Viewer", "permissions": ["kpi.view"]}, "audit.view")
    assert fake.last_error is not None
    assert "audit.view" in fake.last_error
    assert "streamlit.page" in fake.last_error


def test_t15_10_streamlit_require_roles_uses_shared_role_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeStreamlit()
    monkeypatch.setattr(common_mod, "st", fake)
    with pytest.raises(_StopCalled):
        common_mod.require_roles({"role": "Viewer"}, "Admin", "Director")
    assert "Viewer" in (fake.last_error or "")
    assert "Admin, Director" in (fake.last_error or "")
