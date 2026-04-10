"""Settings routes: user profile, connection status."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sample_app.app.auth import require_login
from sample_app.app.meetr_client import MeetrClient


def create_settings_router(templates: Jinja2Templates, meetr: MeetrClient) -> APIRouter:
    """Create settings routes."""
    router = APIRouter(tags=["settings"])

    @router.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        config = request.app.state.config

        return templates.TemplateResponse(
            request, "settings.html",
            {"user": user, "active_page": "settings", "config": config},
        )

    return router
