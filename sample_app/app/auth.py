"""Authentication helpers: password hashing, session guards."""

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_current_user(request: Request) -> dict | None:
    """Extract the current user from the session, or None if not logged in."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": request.session.get("user_email", ""),
        "display_name": request.session.get("user_name", ""),
        "company_name": request.session.get("user_company_name", ""),
    }


def require_login(request: Request) -> dict | RedirectResponse:
    """Return the current user dict, or a redirect to login if not authenticated."""
    user = get_current_user(request)
    if not user:
        base = request.app.state.config.get("base_path", "")
        return RedirectResponse(url=f"{base}/login", status_code=303)
    return user
