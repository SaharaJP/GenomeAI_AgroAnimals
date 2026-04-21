from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from streamlit_app import common as common_mod
from streamlit_app.auth_bridge import store_streamlit_session
from web_cabinet import rbac


class _Sidebar:
    def __init__(self):
        self.messages: list[str] = []

    def success(self, message: str) -> None:
        self.messages.append(message)

    def button(self, _label: str) -> bool:
        return False

    def caption(self, message: str) -> None:
        self.messages.append(str(message))

    def markdown(self, message: str, **_kwargs) -> None:
        self.messages.append(str(message))

    def page_link(self, *args, **kwargs) -> None:
        self.messages.append(f"page_link:{args[0] if args else kwargs.get('page')}")

    def error(self, message: str) -> None:
        self.messages.append(str(message))

    def header(self, message: str) -> None:
        self.messages.append(str(message))

    def text_input(self, _label: str, value: str = "", **_kwargs) -> str:
        return value


@dataclass
class _FakeStreamlit:
    session_state: dict = field(default_factory=dict)
    sidebar: _Sidebar = field(default_factory=_Sidebar)

    def rerun(self) -> None:
        raise AssertionError("rerun should not be called in this integration test")

    def stop(self) -> None:
        raise AssertionError("stop should not be called in this integration test")

    def error(self, message: str) -> None:
        self.sidebar.error(message)

    def columns(self, spec):
        return (self, self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def markdown(self, _message: str, **_kwargs) -> None:
        return None

    def caption(self, message: str) -> None:
        self.sidebar.messages.append(str(message))

    def divider(self) -> None:
        return None


class _Logger:
    def info(self, *_args, **_kwargs) -> None:
        return None


def test_t18_02_require_user_reuses_bridge_session_and_syncs_active_context(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeStreamlit()
    ctx = common_mod.Context(artifacts_dir=tmp_path / "artifacts", web_storage_dir=tmp_path / "web")
    store_streamlit_session(
        fake.session_state,
        user={
            "id": 7,
            "username": "director",
            "role": rbac.ROLE_DIRECTOR,
            "tenant_id": "default",
            "permissions": tuple(rbac.ROLE_PERMISSIONS[rbac.ROLE_DIRECTOR]),
            "_source": "users_v2",
        },
        request_id="st_req_bridge",
    )
    fake.session_state["director_summary.farm_id"] = "farm_demo"
    fake.session_state["regular_reports.data_version"] = "dv_bridge_01"

    monkeypatch.setattr(common_mod, "st", fake)
    monkeypatch.setattr(common_mod, "streamlit_logger", _Logger())

    user = common_mod.require_user(ctx, render_navigation=False, render_header=False)
    assert user["username"] == "director"
    assert fake.session_state["active_farm"] == "farm_demo"
    assert fake.session_state["active_data_version"] == "dv_bridge_01"
    assert fake.session_state["request_id"] == "st_req_bridge"
