"""Team member routes: list, create, detail, update."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sample_app.app.auth import require_login
from sample_app.app.db import Database
from sample_app.app.main import prefixed_redirect


def create_team_router(templates: Jinja2Templates, db: Database) -> APIRouter:
    """Create team member routes."""
    router = APIRouter(tags=["team"])

    @router.get("/team", response_class=HTMLResponse)
    async def team_list(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        members = await db.list_participants_for_user(user["user_id"])

        return templates.TemplateResponse(
            request, "team/list.html",
            {"user": user, "active_page": "team", "members": members},
        )

    @router.get("/partials/team-rows", response_class=HTMLResponse)
    async def team_rows_partial(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        members = await db.list_participants_for_user(user["user_id"])
        return templates.TemplateResponse(request, "partials/team_rows.html", {"members": members})

    @router.get("/team/new", response_class=HTMLResponse)
    async def create_team_member_form(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        return templates.TemplateResponse(
            request, "team/create.html",
            {"user": user, "active_page": "team", "form": {}, "error": None},
        )

    @router.post("/team")
    async def create_team_member_action(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        form_data = await request.form()
        first_name = form_data.get("first_name", "").strip()
        last_name = form_data.get("last_name", "").strip()
        phone_number = form_data.get("phone_number", "").strip()

        if not first_name or not last_name or not phone_number:
            return templates.TemplateResponse(
                request, "team/create.html",
                {
                    "user": user, "active_page": "team",
                    "form": dict(form_data),
                    "error": "First name, last name, and phone number are required.",
                },
            )

        timezone = form_data.get("timezone", "UTC").strip() or "UTC"
        language = form_data.get("language", "en").strip() or "en"

        modes_str = form_data.get("communication_modes", "")
        modes = []
        if modes_str:
            try:
                parsed = json.loads(modes_str)
                if isinstance(parsed, list):
                    modes = [m for m in parsed if isinstance(m, str)]
            except (json.JSONDecodeError, TypeError):
                pass

        if not modes:
            return templates.TemplateResponse(
                request, "team/create.html",
                {
                    "user": user, "active_page": "team",
                    "form": dict(form_data),
                    "error": "At least one communication channel must be selected.",
                },
            )

        modes_str = json.dumps(modes)

        member = await db.create_participant(
            user_id=user["user_id"],
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            timezone=timezone,
            language=language,
            communication_modes=modes_str,
        )

        return prefixed_redirect(request, f"/team/{member['id']}")

    @router.get("/team/{member_id}", response_class=HTMLResponse)
    async def team_member_detail(request: Request, member_id: int):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        member = await db.get_participant(member_id, user["user_id"])
        if not member:
            return templates.TemplateResponse(
                request, "team/detail.html",
                {"user": user, "active_page": "team", "member": None,
                 "error": "Team member not found."},
                status_code=404,
            )

        channel_list = _parse_channel_list(member.get("communication_modes", "[]"))

        return templates.TemplateResponse(
            request, "team/detail.html",
            {
                "user": user, "active_page": "team",
                "member": member, "channel_list": channel_list,
                "action_result": None,
            },
        )

    @router.post("/team/{member_id}/update")
    async def update_team_member_action(request: Request, member_id: int):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        form_data = await request.form()
        fields = {}
        for field in ("first_name", "last_name", "phone_number", "timezone", "language"):
            val = form_data.get(field, "")
            if val is not None:
                fields[field] = val

        modes_str = form_data.get("communication_modes", "")
        if modes_str:
            try:
                parsed = json.loads(modes_str)
                if isinstance(parsed, list):
                    modes = [m for m in parsed if isinstance(m, str)]
                    if not modes:
                        member = await db.get_participant(member_id, user["user_id"])
                        channel_list = _parse_channel_list(member.get("communication_modes", "[]")) if member else []
                        return templates.TemplateResponse(
                            request, "team/detail.html",
                            {
                                "user": user, "active_page": "team",
                                "member": member, "channel_list": channel_list,
                                "action_result": {"success": False, "message": "At least one communication channel must be selected."},
                            },
                        )
                    fields["communication_modes"] = json.dumps(modes)
            except (json.JSONDecodeError, TypeError):
                pass

        is_active = form_data.get("is_active", "")
        if is_active:
            fields["is_active"] = 1 if is_active.lower() == "true" else 0

        member = await db.update_participant(member_id, user["user_id"], **fields)
        if not member:
            return templates.TemplateResponse(
                request, "team/detail.html",
                {"user": user, "active_page": "team", "member": None,
                 "error": "Team member not found."},
                status_code=404,
            )

        action_msg = "Team member updated."
        channel_list = _parse_channel_list(member.get("communication_modes", "[]"))

        return templates.TemplateResponse(
            request, "team/detail.html",
            {
                "user": user, "active_page": "team",
                "member": member, "channel_list": channel_list,
                "action_result": {"success": True, "message": action_msg},
            },
        )

    return router


def _parse_channel_list(modes_str: str) -> list[str]:
    try:
        modes = json.loads(modes_str) if modes_str else []
        return [m for m in modes if isinstance(m, str)] if isinstance(modes, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
