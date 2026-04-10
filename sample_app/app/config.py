"""Configuration loaded from environment variables or .env file."""

import os
from pathlib import Path

# Base directory for the sample app
BASE_DIR = Path(__file__).parent.parent


def get_config() -> dict:
    """Return configuration from environment variables."""
    return {
        "meetr_api_url": os.getenv("MEETR_API_URL", "https://meetr.aigent.biz"),
        "meetr_api_key": os.getenv("MEETR_API_KEY", ""),
        "meetr_customer_id": os.getenv("MEETR_CUSTOMER_ID", ""),
        "app_port": int(os.getenv("APP_PORT", "80")),
        "app_secret_key": os.getenv("APP_SECRET_KEY", "sample-app-dev-key"),
        "database_path": os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "sample_app.db")),
        "base_path": os.getenv("BASE_PATH", ""),
    }
