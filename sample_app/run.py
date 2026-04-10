#!/usr/bin/env python3
"""Entry point for the Meetr Sample App.

Usage:
    python run.py                 # Normal startup (requires .env / env vars)
    python run.py --auto-setup    # Developer mode: auto-creates partner + admin user
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv

# Ensure sample_app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sample_app.app.config import get_config, BASE_DIR

logger = logging.getLogger("sample_app")

SAMPLE_APP_PARTNER_NAME = "Sample App"
AUTO_SETUP_ADMIN_EMAIL = "admin@example.com"
AUTO_SETUP_ADMIN_PASSWORD = "admin"


async def auto_setup(config: dict) -> None:
    """Idempotent auto-setup: register partner if needed + seed admin user.

    Checks sample_app/.env for an existing MEETR_API_KEY.  If absent,
    calls the Meetr partner registration endpoint to create a new partner
    and persists the returned key to .env so it survives restarts.
    """
    meetr_url = config["meetr_api_url"]
    # Save to data/ directory which is mounted as a Docker volume and persists
    # across container rebuilds. Falls back to BASE_DIR/.env for local dev.
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    env_file = data_dir / ".env" if data_dir.exists() else BASE_DIR / ".env"

    # --- Step 1: Obtain and validate API key --------------------------------
    # Load persisted env file first (survives Docker rebuilds)
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    api_key = os.getenv("MEETR_API_KEY", "").strip()

    if api_key:
        logger.info("Found existing MEETR_API_KEY, validating...")
        # Validate the key — if stale (401), discard and re-register
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{meetr_url}/api/customers",
                    headers={"X-API-Key": api_key},
                )
                if resp.status_code == 401:
                    logger.warning("Persisted API key rejected (401) — discarding and re-registering")
                    api_key = ""
                    os.environ.pop("MEETR_API_KEY", None)
                else:
                    logger.info("API key validated successfully")
        except httpx.ConnectError:
            logger.error(
                f"Cannot connect to Meetr server at {meetr_url}. "
                "Make sure the Meetr server is running."
            )
            sys.exit(1)

    if not api_key:
        logger.info("Registering partner to obtain API key...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{meetr_url}/api/partners/register",
                    json={"name": SAMPLE_APP_PARTNER_NAME},
                )
            except httpx.ConnectError:
                logger.error(
                    f"Cannot connect to Meetr server at {meetr_url}. "
                    "Make sure the Meetr server is running."
                )
                sys.exit(1)

            if resp.status_code != 200:
                logger.error(
                    f"Partner registration failed ({resp.status_code}): {resp.text}"
                )
                sys.exit(1)

            result = resp.json()
            api_key = result.get("api_key")
            if not api_key:
                logger.error(
                    f"Partner '{result.get('name')}' registration returned no key. "
                    f"Check meetr server logs."
                )
                sys.exit(1)
            logger.info(f"Registered partner '{result['name']}' (id={result['partner_id']})")

        # Persist to .env so we don't re-register on next restart
        _save_env_key(env_file, "MEETR_API_KEY", api_key)
        logger.info(f"Saved MEETR_API_KEY to {env_file}")

    # --- Step 1b: Ensure we have a customer ID ----------------------------
    customer_id = os.getenv("MEETR_CUSTOMER_ID", "").strip()
    if not customer_id:
        logger.info("No MEETR_CUSTOMER_ID found — creating default customer...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{meetr_url}/api/customers",
                headers={"X-API-Key": api_key},
                json={"external_id": "sample-app-default", "name": "Sample App Customer"},
            )
            if resp.status_code in (200, 201):
                customer_id = resp.json().get("id", "")
                logger.info(f"Created customer: {customer_id}")
                _save_env_key(env_file, "MEETR_CUSTOMER_ID", customer_id)
            elif resp.status_code == 409:
                # Customer already exists — look it up
                logger.info("Customer already exists, fetching...")
                list_resp = await client.get(
                    f"{meetr_url}/api/customers",
                    headers={"X-API-Key": api_key},
                )
                if list_resp.status_code == 200:
                    customers = list_resp.json().get("customers", list_resp.json().get("data", []))
                    for c in customers:
                        if c.get("external_id") == "sample-app-default":
                            customer_id = c["id"]
                            break
                if customer_id:
                    logger.info(f"Found existing customer: {customer_id}")
                    _save_env_key(env_file, "MEETR_CUSTOMER_ID", customer_id)
                else:
                    logger.error("Could not find existing customer")
                    sys.exit(1)
            else:
                logger.error(f"Failed to create customer ({resp.status_code}): {resp.text}")
                sys.exit(1)

    os.environ["MEETR_CUSTOMER_ID"] = customer_id

    # Make key available to the app process
    os.environ["MEETR_API_KEY"] = api_key

    # --- Step 2: Seed local database (admin user) -------------------------
    from sample_app.app.db import Database
    from sample_app.app.auth import hash_password

    db = Database(config["database_path"])
    await db.connect()
    try:
        user_count = await db.user_count()
        if user_count == 0:
            await db.create_user(
                email=AUTO_SETUP_ADMIN_EMAIL,
                password_hash=hash_password(AUTO_SETUP_ADMIN_PASSWORD),
                display_name="Admin",
                company_name=SAMPLE_APP_PARTNER_NAME,
            )
            logger.info(f"Created admin user: {AUTO_SETUP_ADMIN_EMAIL}")
    finally:
        await db.close()


def _save_env_key(env_file: Path, key: str, value: str) -> None:
    """Append or update a key=value pair in the .env file."""
    lines = []
    found = False
    if env_file.exists():
        lines = env_file.read_text().splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"# {key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}\n")
    env_file.write_text("".join(lines))


def print_banner(config: dict, is_auto_setup: bool) -> None:
    """Print startup banner."""
    port = config["app_port"]
    meetr_url = config["meetr_api_url"]
    key_preview = config["meetr_api_key"][:20] + "..." if len(config.get("meetr_api_key", "")) > 20 else config.get("meetr_api_key", "")

    lines = [
        "Sample App" + (" (auto-setup mode)" if is_auto_setup else ""),
        "-" * 50,
        f"  Meetr service:  {meetr_url}",
        f"  API key:        {key_preview}",
    ]
    if is_auto_setup:
        lines.append(f"  Admin login:    {AUTO_SETUP_ADMIN_EMAIL} / {AUTO_SETUP_ADMIN_PASSWORD}")
    lines.append("-" * 50)
    lines.append(f"  App running at: http://localhost:{port}")

    border = "+" + "=" * 54 + "+"
    print(f"\n{border}")
    for line in lines:
        print(f"|  {line:<52}|")
    print(f"{border}\n")


def main():
    parser = argparse.ArgumentParser(description="Meetr Sample App")
    parser.add_argument("--auto-setup", action="store_true", help="Auto-create partner and seed admin user")
    parser.add_argument("--port", type=int, default=None, help="Override APP_PORT")
    args = parser.parse_args()

    # Load .env if present
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    config = get_config()
    if args.port:
        config["app_port"] = args.port

    if args.auto_setup:
        asyncio.run(auto_setup(config))
        # Refresh config after auto-setup may have set env vars
        config = get_config()

    print_banner(config, args.auto_setup)

    uvicorn.run(
        "sample_app.app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=config["app_port"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
