"""Authentication routes: login, logout, register."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sample_app.app.auth import hash_password, verify_password
from sample_app.app.db import Database
from sample_app.app.main import prefixed_redirect

logger = logging.getLogger(__name__)


def create_auth_router(templates: Jinja2Templates, db: Database) -> APIRouter:
    """Create authentication routes."""
    router = APIRouter(tags=["auth"])

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        """Show the login form."""
        if request.session.get("user_id"):
            return prefixed_redirect(request, "/")

        return templates.TemplateResponse(request, "login.html", {"error": None})

    @router.post("/login", response_class=HTMLResponse)
    async def login_action(request: Request):
        """Authenticate with email + password."""
        form = await request.form()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")

        if not email or not password:
            return templates.TemplateResponse(
                request, "login.html", {"error": "Email and password are required."}
            )

        user = await db.get_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(
                request, "login.html", {"error": "Invalid email or password."}
            )

        if not user["is_active"]:
            return templates.TemplateResponse(
                request, "login.html", {"error": "Account is disabled."}
            )

        # Set session
        request.session["user_id"] = user["id"]
        request.session["user_email"] = user["email"]
        request.session["user_name"] = user["display_name"]
        request.session["user_company_name"] = user["company_name"]

        return prefixed_redirect(request, "/")

    @router.get("/register", response_class=HTMLResponse)
    async def register_page(request: Request):
        """Show the registration form."""
        if request.session.get("user_id"):
            return prefixed_redirect(request, "/")

        return templates.TemplateResponse(request, "register.html", {"error": None})

    @router.post("/register", response_class=HTMLResponse)
    async def register_action(request: Request):
        """Create a new user account."""
        form = await request.form()
        display_name = form.get("display_name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        password_confirm = form.get("password_confirm", "")
        company_name = form.get("company_name", "").strip()

        if not display_name or not email or not password or not company_name:
            return templates.TemplateResponse(
                request, "register.html", {"error": "All fields are required."}
            )

        if password != password_confirm:
            return templates.TemplateResponse(
                request, "register.html", {"error": "Passwords do not match."}
            )

        if len(password) < 4:
            return templates.TemplateResponse(
                request, "register.html", {"error": "Password must be at least 4 characters."}
            )

        # Check if email already taken
        existing = await db.get_user_by_email(email)
        if existing:
            return templates.TemplateResponse(
                request, "register.html", {"error": "An account with that email already exists."}
            )

        await db.create_user(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            company_name=company_name,
        )

        logger.info(f"New user registered: '{email}'")
        return prefixed_redirect(request, "/login")

    @router.post("/logout")
    async def logout_action(request: Request):
        """Clear session and redirect to login."""
        request.session.clear()
        return prefixed_redirect(request, "/login")

    return router
