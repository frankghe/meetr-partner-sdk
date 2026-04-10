"""Tests for authentication: login, logout, register."""

import pytest
from httpx import ASGITransport, AsyncClient

from sample_app.app.auth import hash_password, verify_password
from sample_app.app.main import create_app
from sample_app.tests.conftest import login_client


def _make_client(config, db):
    """Helper: create app + test client (db already connected, lifespan skipped)."""
    app = create_app(config=config, db=db)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h)
        assert not verify_password("wrong", h)

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestRegistration:
    @pytest.mark.asyncio
    async def test_register_page_renders(self, db, config):
        """Registration page renders."""
        async with _make_client(config, db) as client:
            resp = await client.get("/register")
            assert resp.status_code == 200
            assert "Create Account" in resp.text
            assert "Company Name" in resp.text

    @pytest.mark.asyncio
    async def test_register_creates_user(self, db, config):
        """Registration creates a user with company_name."""
        async with _make_client(config, db) as client:
            resp = await client.post(
                "/register",
                data={
                    "display_name": "Alice",
                    "company_name": "Alice Corp",
                    "email": "alice@test.com",
                    "password": "secret123",
                    "password_confirm": "secret123",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/login"

        user = await db.get_user_by_email("alice@test.com")
        assert user["display_name"] == "Alice"
        assert user["company_name"] == "Alice Corp"

    @pytest.mark.asyncio
    async def test_register_password_mismatch(self, db, config):
        """Registration fails if passwords don't match."""
        async with _make_client(config, db) as client:
            resp = await client.post(
                "/register",
                data={
                    "display_name": "Bob",
                    "company_name": "Bob Inc",
                    "email": "bob@test.com",
                    "password": "pass1234",
                    "password_confirm": "different",
                },
            )
            assert resp.status_code == 200
            assert "Passwords do not match" in resp.text


class TestLoginLogout:
    @pytest.mark.asyncio
    async def test_login_page_renders(self, client):
        resp = await client.get("/login")
        assert resp.status_code == 200
        assert "Sample App" in resp.text
        assert "Email" in resp.text

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        resp = await client.post(
            "/login",
            data={"email": "admin@test.com", "password": "testpass"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_login_bad_password(self, client):
        resp = await client.post(
            "/login",
            data={"email": "admin@test.com", "password": "wrong"},
        )
        assert resp.status_code == 200
        assert "Invalid email or password" in resp.text

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client):
        resp = await client.post(
            "/login",
            data={"email": "nobody@test.com", "password": "test"},
        )
        assert resp.status_code == 200
        assert "Invalid email or password" in resp.text

    @pytest.mark.asyncio
    async def test_logout(self, client):
        await login_client(client)
        resp = await client.post("/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    @pytest.mark.asyncio
    async def test_protected_page_redirects_when_not_logged_in(self, client):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    @pytest.mark.asyncio
    async def test_dashboard_accessible_when_logged_in(self, client):
        await login_client(client)
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 200
