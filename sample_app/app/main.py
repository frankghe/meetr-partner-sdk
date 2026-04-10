"""FastAPI application factory for the sample app."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sample_app.app.config import get_config
from sample_app.app.db import Database
from sample_app.app.meetr_client import MeetrClient

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def prefixed_redirect(request, path: str, status_code: int = 303):
    """Create a RedirectResponse with the configured base_path prefix."""
    from fastapi.responses import RedirectResponse
    base = request.app.state.config.get("base_path", "")
    return RedirectResponse(url=f"{base}{path}", status_code=status_code)


def create_app(config: dict | None = None, db: Database | None = None, meetr: MeetrClient | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Optional config dict (defaults to get_config()).
        db: Optional Database instance (for testing).
        meetr: Optional MeetrClient instance (for testing).
    """
    if config is None:
        config = get_config()

    _db_provided = db is not None

    if db is None:
        db = Database(config["database_path"])
    if meetr is None:
        meetr = MeetrClient(
            base_url=config["meetr_api_url"],
            api_key=config["meetr_api_key"],
            customer_id=config["meetr_customer_id"],
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        logger.info("Sample app database connected")
        yield
        await db.close()
        await meetr.close()
        logger.info("Sample app shut down")

    # Skip lifespan when db is injected (testing) — caller manages lifecycle
    kwargs = {} if _db_provided else {"lifespan": lifespan}
    app = FastAPI(title="Meetr Sample App", docs_url=None, redoc_url=None, **kwargs)

    # Session middleware (signed cookies)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config["app_secret_key"],
        session_cookie="sample_app_session",
        max_age=86400,
    )

    app.state.db = db
    app.state.meetr = meetr
    app.state.config = config

    # Templates
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # Make base_path available in all templates
    templates.env.globals["base_path"] = config.get("base_path", "")

    # --- Routes ---
    from sample_app.app.routes.auth_routes import create_auth_router
    from sample_app.app.routes.dashboard import create_dashboard_router
    from sample_app.app.routes.meetings import create_meetings_router
    from sample_app.app.routes.team import create_team_router
    from sample_app.app.routes.settings import create_settings_router

    app.include_router(create_auth_router(templates, db))
    app.include_router(create_dashboard_router(templates, meetr))
    app.include_router(create_meetings_router(templates, meetr, db))
    app.include_router(create_team_router(templates, db))
    app.include_router(create_settings_router(templates, meetr))

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
