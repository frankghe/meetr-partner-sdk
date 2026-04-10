"""Tests for database operations."""

import pytest

from sample_app.app.auth import hash_password
from sample_app.app.db import Database


class TestUsers:
    @pytest.mark.asyncio
    async def test_no_users_initially(self, db):
        assert await db.user_count() == 0
        assert await db.list_users() == []

    @pytest.mark.asyncio
    async def test_create_user(self, db):
        user = await db.create_user("alice@test.com", hash_password("pass"), "Alice", "Acme Corp")
        assert user["email"] == "alice@test.com"
        assert user["display_name"] == "Alice"
        assert user["company_name"] == "Acme Corp"
        assert await db.user_count() == 1

    @pytest.mark.asyncio
    async def test_create_user_default_company(self, db):
        user = await db.create_user("bob@test.com", hash_password("pass"), "Bob", "Bob's Inc")
        assert user["company_name"] == "Bob's Inc"

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, db):
        await db.create_user("bob@test.com", hash_password("pass"), "Bob", "Test Co")
        user = await db.get_user_by_email("bob@test.com")
        assert user["display_name"] == "Bob"
        assert await db.get_user_by_email("nobody@test.com") is None

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db):
        created = await db.create_user("carol@test.com", hash_password("pass"), "Carol", "Carol Co")
        user = await db.get_user_by_id(created["id"])
        assert user["email"] == "carol@test.com"
        assert await db.get_user_by_id(9999) is None

    @pytest.mark.asyncio
    async def test_list_users(self, db):
        await db.create_user("a@test.com", hash_password("p"), "A", "Co A")
        await db.create_user("b@test.com", hash_password("p"), "B", "Co B")
        users = await db.list_users()
        assert len(users) == 2


class TestParticipants:
    @pytest.mark.asyncio
    async def test_no_participants_initially(self, db):
        user = await db.create_user("owner@test.com", hash_password("p"), "Owner", "Test Co")
        members = await db.list_participants_for_user(user["id"])
        assert members == []

    @pytest.mark.asyncio
    async def test_create_participant(self, db):
        user = await db.create_user("owner@test.com", hash_password("p"), "Owner", "Test Co")
        member = await db.create_participant(
            user_id=user["id"],
            first_name="Jane",
            last_name="Doe",
            phone_number="+1234567890",
        )
        assert member["first_name"] == "Jane"
        assert member["last_name"] == "Doe"
        assert member["phone_number"] == "+1234567890"
        assert member["timezone"] == "UTC"
        assert member["language"] == "en"
        assert member["is_active"] == 1

    @pytest.mark.asyncio
    async def test_list_participants_scoped_to_user(self, db):
        user1 = await db.create_user("u1@test.com", hash_password("p"), "U1", "Co1")
        user2 = await db.create_user("u2@test.com", hash_password("p"), "U2", "Co2")
        await db.create_participant(user1["id"], "Alice", "A", "+111")
        await db.create_participant(user2["id"], "Bob", "B", "+222")

        u1_members = await db.list_participants_for_user(user1["id"])
        u2_members = await db.list_participants_for_user(user2["id"])
        assert len(u1_members) == 1
        assert u1_members[0]["first_name"] == "Alice"
        assert len(u2_members) == 1
        assert u2_members[0]["first_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_participant_scoped(self, db):
        user1 = await db.create_user("u1@test.com", hash_password("p"), "U1", "Co1")
        user2 = await db.create_user("u2@test.com", hash_password("p"), "U2", "Co2")
        member = await db.create_participant(user1["id"], "Alice", "A", "+111")

        # User 1 can see it
        assert await db.get_participant(member["id"], user1["id"]) is not None
        # User 2 cannot
        assert await db.get_participant(member["id"], user2["id"]) is None

    @pytest.mark.asyncio
    async def test_update_participant(self, db):
        user = await db.create_user("owner@test.com", hash_password("p"), "Owner", "Test Co")
        member = await db.create_participant(user["id"], "Jane", "Doe", "+111")

        updated = await db.update_participant(member["id"], user["id"], first_name="Janet", timezone="US/Eastern")
        assert updated["first_name"] == "Janet"
        assert updated["timezone"] == "US/Eastern"
        assert updated["last_name"] == "Doe"  # unchanged
