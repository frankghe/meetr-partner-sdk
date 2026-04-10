"""Test fixtures for sample_app tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sample_app.app.auth import hash_password
from sample_app.app.db import Database
from sample_app.app.main import create_app


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_sample_app.db")
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def seeded_db(db):
    """Database with an admin user already created."""
    await db.create_user(
        email="admin@test.com",
        password_hash=hash_password("testpass"),
        display_name="Test Admin",
        company_name="Test Corp",
    )
    return db


@pytest.fixture
def config(tmp_path):
    """Test configuration."""
    return {
        "meetr_api_url": "http://localhost:8001",
        "meetr_api_key": "mk_test_key_12345",
        "meetr_customer_id": "test-customer-id",
        "app_port": 8002,
        "app_secret_key": "test-secret-key",
        "database_path": str(tmp_path / "test_sample_app.db"),
    }


@pytest.fixture
def mock_meetr():
    """Mock MeetrClient that returns empty successful responses."""
    meetr = MagicMock()
    meetr.list_meetings = AsyncMock(return_value={"status": 200, "data": {"data": []}})
    meetr.close = AsyncMock()
    return meetr


@pytest_asyncio.fixture
async def app(seeded_db, config, mock_meetr):
    """Create test app with seeded database (lifespan skipped, db pre-connected)."""
    return create_app(config=config, db=seeded_db, meetr=mock_meetr)


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def login_client(client: AsyncClient, email: str = "admin@test.com", password: str = "testpass") -> AsyncClient:
    """Log in and return the client with session cookies."""
    resp = await client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert resp.status_code == 303
    return client
