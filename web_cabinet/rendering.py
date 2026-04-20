from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates


def render_template(
    templates: Jinja2Templates,
    request: Request,
    name: str,
    *,
    settings: Any,
    **ctx: Any,
):
    """Render Jinja template using the current Starlette/FastAPI contract.

    The helper preserves the existing page context surface while routing all
    template rendering through the request-first ``TemplateResponse`` API.
    """
    if "active" not in ctx:
        seg = request.url.path.strip("/").split("/")[0]
        ctx["active"] = seg or ""
    context = {"request": request, "settings": settings, **ctx}
    return templates.TemplateResponse(request, name, context)
