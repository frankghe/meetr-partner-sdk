"""Dashboard route."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sample_app.app.auth import require_login
from sample_app.app.meetr_client import MeetrClient

def create_dashboard_router(templates: Jinja2Templates, meetr: MeetrClient) -> APIRouter:
    """Create dashboard routes."""
    router = APIRouter(tags=["dashboard"])

    @router.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        # Fetch recent meetings
        result = await meetr.list_meetings()
        meetings = []
        if result["status"] == 200:
            data = result["data"]
            meetings = data.get("data", data) if isinstance(data, dict) else data

        # Compute stats
        stats = {"total": 0, "active": 0, "completed": 0, "failed": 0}
        if isinstance(meetings, list):
            stats["total"] = len(meetings)
            for m in meetings:
                state = m.get("state", "")
                if state == "COMPLETED":
                    stats["completed"] += 1
                elif state == "FAILED":
                    stats["failed"] += 1
                elif state not in ("COMPLETED", "FAILED", "CANCELLED"):
                    stats["active"] += 1

        recent = meetings[:10] if isinstance(meetings, list) else []

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "user": user,
                "active_page": "dashboard",
                "stats": stats,
                "recent_meetings": recent,
            },
        )

    @router.get("/partials/dashboard-stats", response_class=HTMLResponse)
    async def dashboard_stats_partial(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        result = await meetr.list_meetings()
        meetings = []
        if result["status"] == 200:
            data = result["data"]
            meetings = data.get("data", data) if isinstance(data, dict) else data

        stats = {"total": 0, "active": 0, "completed": 0, "failed": 0}
        if isinstance(meetings, list):
            stats["total"] = len(meetings)
            for m in meetings:
                state = m.get("state", "")
                if state == "COMPLETED":
                    stats["completed"] += 1
                elif state == "FAILED":
                    stats["failed"] += 1
                elif state not in ("COMPLETED", "FAILED", "CANCELLED"):
                    stats["active"] += 1

        return templates.TemplateResponse(
            request,
            "partials/dashboard_stats.html",
            {"stats": stats, "user": user},
        )

    return router
