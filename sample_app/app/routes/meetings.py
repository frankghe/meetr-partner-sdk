"""Meeting routes: list, create, detail, actions, SSE."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from sample_app.app.auth import require_login
from sample_app.app.db import Database
from sample_app.app.main import prefixed_redirect
from sample_app.app.meetr_client import MeetrClient

logger = logging.getLogger(__name__)

MEETING_STATES = [
    "PENDING", "COLLECTING", "AWAITING_RESPONSES",
    "SELECTING_SLOT", "NEEDS_INTERVENTION", "CONFIRMING", "AWAITING_CONFIRMATIONS",
    "COMPLETED", "FAILED", "CANCELLED",
]

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}

def _parse_channel_list(modes_str: str) -> list[str]:
    try:
        modes = json.loads(modes_str) if modes_str else []
        return [m for m in modes if isinstance(m, str)] if isinstance(modes, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def create_meetings_router(templates: Jinja2Templates, meetr: MeetrClient, db: Database) -> APIRouter:
    """Create meeting routes."""
    router = APIRouter(tags=["meetings"])

    @router.get("/meetings", response_class=HTMLResponse)
    async def meeting_list(request: Request, state: str = "", requester: str = ""):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        result = await meetr.list_meetings(state=state or None)
        meetings = []
        error = None
        if result["status"] == 200:
            data = result["data"]
            meetings = data.get("data", data) if isinstance(data, dict) else data
            if not isinstance(meetings, list):
                meetings = []
            if requester:
                rl = requester.lower()
                meetings = [m for m in meetings if rl in (m.get("customer_name") or "").lower()]
        else:
            error = result["data"].get("detail", "Failed to load meetings")

        return templates.TemplateResponse(
            request, "meetings/list.html",
            {
                "user": user, "active_page": "meetings",
                "meetings": meetings, "states": MEETING_STATES,
                "current_state": state, "current_requester": requester,
                "error": error,
            },
        )

    @router.get("/partials/meeting-rows", response_class=HTMLResponse)
    async def meeting_rows_partial(request: Request, state: str = "", requester: str = ""):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        result = await meetr.list_meetings(state=state or None)
        meetings = []
        if result["status"] == 200:
            data = result["data"]
            meetings = data.get("data", data) if isinstance(data, dict) else data
            if not isinstance(meetings, list):
                meetings = []
            if requester:
                rl = requester.lower()
                meetings = [m for m in meetings if rl in (m.get("customer_name") or "").lower()]

        return templates.TemplateResponse(request, "partials/meeting_rows.html", {"meetings": meetings})

    @router.get("/meetings/new", response_class=HTMLResponse)
    async def create_meeting_form(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        # Fetch team members from local DB (not Meetr API)
        team_members = await db.list_participants_for_user(user["user_id"])

        form = {}
        prefill_member_ids = []
        source_id = request.query_params.get("from")
        if source_id:
            result = await meetr.get_meeting(source_id)
            if result["status"] == 200:
                m = result["data"].get("data", result["data"])
                window = m.get("scheduling_window", {})
                form = {
                    "purpose": m.get("meeting_purpose") or m.get("purpose", ""),
                    "context": m.get("context", ""),
                    "scheduling_window_start": (window.get("start", "") or "")[:16],
                    "scheduling_window_end": (window.get("end", "") or "")[:16],
                    "timezone": window.get("timezone", "Asia/Jerusalem"),
                    "meeting_duration_minutes": str(m.get("meeting_duration_minutes", 60)),
                    "max_scheduling_deadline": (m.get("max_scheduling_deadline") or "")[:16],
                    "external_id": m.get("external_id", "") or "",
                }

        return templates.TemplateResponse(
            request, "meetings/create.html",
            {
                "user": user, "active_page": "meetings",
                "form": form, "team_members": team_members,
                "prefill_member_ids": prefill_member_ids, "error": None,
            },
        )

    @router.post("/meetings")
    async def create_meeting_action(request: Request):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        form_data = await request.form()

        # Get selected team member IDs
        member_ids = form_data.getlist("member_ids")
        if not member_ids:
            team_members = await db.list_participants_for_user(user["user_id"])
            return templates.TemplateResponse(
                request, "meetings/create.html",
                {
                    "user": user, "active_page": "meetings",
                    "form": dict(form_data), "team_members": team_members,
                    "error": "At least one team member must be selected.",
                },
            )

        # Build participant list from selected team members
        participants = []
        for mid in member_ids:
            member = await db.get_participant(int(mid), user["user_id"])
            if member:
                priority_key = f"priority_{mid}"
                priority = int(form_data.get(priority_key, "3"))
                participants.append({
                    "first_name": member["first_name"],
                    "last_name": member["last_name"],
                    "phone_number": member["phone_number"],
                    "timezone": member.get("timezone", "UTC"),
                    "language": member.get("language", "en"),
                    "communication_modes": _parse_channel_list(member.get("communication_modes", '["whatsapp"]')),
                    "priority": priority,
                })

        meeting_data = {
            "purpose": form_data.get("purpose", ""),
            "context": form_data.get("context", ""),
            "scheduling_window_start": form_data.get("scheduling_window_start", ""),
            "scheduling_window_end": form_data.get("scheduling_window_end", ""),
            "timezone": form_data.get("timezone", "Asia/Jerusalem"),
            "meeting_duration_minutes": int(form_data.get("meeting_duration_minutes", 60)),
            "participants": participants,
            "requester": form_data.get("requester", user.get("display_name", "sample_app")),
        }

        for field in ("max_scheduling_deadline", "external_id", "client_callback_url"):
            val = form_data.get(field, "")
            if val:
                meeting_data[field] = val

        min_p = form_data.get("min_participants_required", "")
        if min_p:
            meeting_data["min_participants_required"] = int(min_p)

        manager_id = form_data.get("manager_id", "")
        if manager_id:
            manager_member = await db.get_participant(int(manager_id), user["user_id"])
            if manager_member:
                meeting_data["manager"] = {
                    "first_name": manager_member["first_name"],
                    "last_name": manager_member["last_name"],
                    "phone_number": manager_member["phone_number"],
                    "timezone": manager_member.get("timezone", "UTC"),
                    "language": manager_member.get("language", "en"),
                    "communication_modes": _parse_channel_list(manager_member.get("communication_modes", '["whatsapp"]')),
                }

        intervention_notification = form_data.get("intervention_notification", "")
        if intervention_notification:
            meeting_data["intervention_notification"] = intervention_notification

        result = await meetr.create_meeting(meeting_data)

        if result["status"] == 200:
            session_id = result["data"].get("session_id", "")
            return prefixed_redirect(request, f"/meetings/{session_id}")

        error_detail = result["data"].get("detail", "Failed to create meeting")
        team_members = await db.list_participants_for_user(user["user_id"])
        return templates.TemplateResponse(
            request, "meetings/create.html",
            {
                "user": user, "active_page": "meetings",
                "form": dict(form_data), "team_members": team_members,
                "error": f"Error: {error_detail}",
            },
        )

    @router.get("/meetings/{meeting_id}", response_class=HTMLResponse)
    async def meeting_detail(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        result = await meetr.get_meeting(meeting_id)
        if result["status"] != 200:
            return templates.TemplateResponse(
                request, "meetings/detail.html",
                {
                    "user": user, "active_page": "meetings",
                    "meeting": None, "error": result["data"].get("detail", "Meeting not found"),
                },
                status_code=404,
            )

        meeting = result["data"].get("data", result["data"])
        meeting["is_terminal"] = meeting.get("state", "") in TERMINAL_STATES

        return templates.TemplateResponse(
            request, "meetings/detail.html",
            {
                "user": user, "active_page": "meetings",
                "meeting": meeting, "meeting_id": meeting_id,
                "error": None, "action_result": None,
            },
        )

    @router.get("/partials/participant-cards/{meeting_id}", response_class=HTMLResponse)
    async def participant_cards_partial(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        result = await meetr.get_meeting(meeting_id)
        raw = result["data"] if result["status"] == 200 else {}
        meeting = raw.get("data", raw) if isinstance(raw, dict) else raw

        return templates.TemplateResponse(
            request, "partials/participant_cards.html",
            {"meeting": meeting, "meeting_id": meeting_id},
        )

    async def _action_and_refetch(request, user, meeting_id, action_coro, success_msg):
        """Common pattern: perform action, re-fetch meeting, render detail."""
        result = await action_coro
        action_msg = success_msg if result["status"] == 200 else result["data"].get("detail", "Action failed")

        meeting_result = await meetr.get_meeting(meeting_id)
        raw_m = meeting_result["data"] if meeting_result["status"] == 200 else None
        meeting = raw_m.get("data", raw_m) if isinstance(raw_m, dict) else raw_m
        if meeting:
            meeting["is_terminal"] = meeting.get("state", "") in TERMINAL_STATES

        return templates.TemplateResponse(
            request, "meetings/detail.html",
            {
                "user": user, "active_page": "meetings",
                "meeting": meeting, "meeting_id": meeting_id,
                "error": None if result["status"] == 200 else action_msg,
                "action_result": {"success": result["status"] == 200, "message": action_msg},
            },
        )

    @router.post("/meetings/{meeting_id}/cancel")
    async def cancel_meeting_action(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user
        return await _action_and_refetch(
            request, user, meeting_id, meetr.cancel_meeting(meeting_id), "Meeting cancelled.",
        )

    @router.post("/meetings/{meeting_id}/select-slot")
    async def select_slot_action(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user
        return await _action_and_refetch(
            request, user, meeting_id, meetr.select_slot(meeting_id), "Slot selection triggered.",
        )

    @router.post("/meetings/{meeting_id}/notify")
    async def notify_action(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user
        return await _action_and_refetch(
            request, user, meeting_id, meetr.notify_participants(meeting_id), "Notifications sent.",
        )

    @router.post("/meetings/{meeting_id}/intervene")
    async def intervene_action(request: Request, meeting_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        form = await request.form()
        message = form.get("intervention_message", "")
        if not message:
            meeting_result = await meetr.get_meeting(meeting_id)
            raw_m = meeting_result["data"] if meeting_result["status"] == 200 else None
            meeting = raw_m.get("data", raw_m) if isinstance(raw_m, dict) else raw_m
            if meeting:
                meeting["is_terminal"] = meeting.get("state", "") in TERMINAL_STATES
            return templates.TemplateResponse(
                request, "meetings/detail.html",
                {
                    "user": user, "active_page": "meetings",
                    "meeting": meeting, "meeting_id": meeting_id,
                    "action_result": {"success": False, "message": "Please provide an intervention instruction."},
                },
            )

        result = await meetr.intervene(meeting_id, message)
        if result["status"] == 200:
            resp_data = result["data"]
            if isinstance(resp_data, dict) and "data" in resp_data:
                resp_data = resp_data["data"]
            actions = resp_data.get("actions_applied", [])
            errors = resp_data.get("validation_errors", [])
            new_state = resp_data.get("new_state", "")
            action_msg = f"Intervention applied: {', '.join(actions)}" if actions else "No actions applied"
            if errors:
                action_msg += f" (warnings: {', '.join(errors)})"
            if new_state:
                action_msg += f" -> {new_state}"
            success = resp_data.get("success", False)
        else:
            action_msg = result["data"].get("detail", "Intervention failed")
            success = False

        meeting_result = await meetr.get_meeting(meeting_id)
        raw_m = meeting_result["data"] if meeting_result["status"] == 200 else None
        meeting = raw_m.get("data", raw_m) if isinstance(raw_m, dict) else raw_m
        if meeting:
            meeting["is_terminal"] = meeting.get("state", "") in TERMINAL_STATES

        return templates.TemplateResponse(
            request, "meetings/detail.html",
            {
                "user": user, "active_page": "meetings",
                "meeting": meeting, "meeting_id": meeting_id,
                "action_result": {"success": success, "message": action_msg},
            },
        )

    # --- Outreach Actions ---

    @router.post("/meetings/{meeting_id}/outreach/{participant_id}/start")
    async def start_outreach_action(request: Request, meeting_id: str, participant_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user
        return await _action_and_refetch(
            request, user, meeting_id, meetr.start_outreach(meeting_id, participant_id), "Outreach started.",
        )

    @router.post("/meetings/{meeting_id}/outreach/{participant_id}/force-fail")
    async def force_fail_outreach_action(request: Request, meeting_id: str, participant_id: str):
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user
        return await _action_and_refetch(
            request, user, meeting_id, meetr.force_fail_outreach(meeting_id, participant_id), "Outreach force-failed.",
        )

    # --- SSE Proxy ---

    @router.get("/sse/meetings/{meeting_id}")
    async def sse_proxy(request: Request, meeting_id: str):
        """Proxy SSE events from the Meetr service."""
        user = require_login(request)
        if isinstance(user, RedirectResponse):
            return user

        async def event_stream():
            try:
                async with meetr._http.stream(
                    "GET",
                    f"{meetr._base_url}/api/meetings/{meeting_id}/events",
                    headers=meetr._headers(),
                    timeout=None,
                ) as response:
                    async for line in response.aiter_lines():
                        if await request.is_disconnected():
                            break
                        yield line + "\n"
            except Exception as e:
                logger.warning(f"SSE proxy error: {e}")
                yield f"event: error\ndata: {{\"message\": \"Connection lost\"}}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router
