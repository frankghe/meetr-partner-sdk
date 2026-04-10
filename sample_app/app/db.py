"""SQLite database for the sample app (users, participants)."""

import aiosqlite
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    language TEXT DEFAULT 'en',
    communication_modes TEXT DEFAULT '["whatsapp"]',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and create tables if needed. Idempotent."""
        if self._db is not None:
            return
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    # --- Users ---

    async def get_user_by_email(self, email: str) -> dict | None:
        """Look up a user by email."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> dict | None:
        """Look up a user by ID."""
        async with self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, email: str, password_hash: str, display_name: str, company_name: str) -> dict:
        """Create a new user."""
        await self.conn.execute(
            "INSERT INTO users (email, password_hash, display_name, company_name) VALUES (?, ?, ?, ?)",
            (email, password_hash, display_name, company_name),
        )
        await self.conn.commit()
        return await self.get_user_by_email(email)

    async def list_users(self) -> list[dict]:
        """List all users."""
        async with self.conn.execute("SELECT * FROM users ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def user_count(self) -> int:
        """Return the number of users."""
        async with self.conn.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    # --- Participants ---

    async def list_participants_for_user(self, user_id: int) -> list[dict]:
        """List all participants belonging to a user."""
        async with self.conn.execute(
            "SELECT * FROM participants WHERE user_id = ? ORDER BY created_at", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_participant(self, participant_id: int, user_id: int) -> dict | None:
        """Get a participant by ID, scoped to a user."""
        async with self.conn.execute(
            "SELECT * FROM participants WHERE id = ? AND user_id = ?", (participant_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_participant(self, user_id: int, first_name: str, last_name: str, phone_number: str, timezone: str = "UTC", language: str = "en", communication_modes: str = '["whatsapp"]') -> dict:
        """Create a new participant for a user."""
        cursor = await self.conn.execute(
            "INSERT INTO participants (user_id, first_name, last_name, phone_number, timezone, language, communication_modes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, first_name, last_name, phone_number, timezone, language, communication_modes),
        )
        await self.conn.commit()
        return await self.get_participant(cursor.lastrowid, user_id)

    async def update_participant(self, participant_id: int, user_id: int, **fields) -> dict | None:
        """Update a participant's fields. Only updates provided fields."""
        allowed = {"first_name", "last_name", "phone_number", "timezone", "language", "communication_modes", "is_active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get_participant(participant_id, user_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [participant_id, user_id]
        await self.conn.execute(
            f"UPDATE participants SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        await self.conn.commit()
        return await self.get_participant(participant_id, user_id)
