"""SQLite initialization and readiness checks."""

import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA_VERSION = "3"


def initialize_database(database_path: Path) -> None:
    """Create the local database and its schema-version metadata."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO app_metadata (key, value)
                VALUES ('schema_version', ?)
                """,
                (SCHEMA_VERSION,),
            )
            connection.execute(
                """
                UPDATE app_metadata
                SET value = ?
                WHERE key = 'schema_version' AND value IN ('1', '2')
                """,
                (SCHEMA_VERSION,),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    salt BLOB NOT NULL,
                    verifier BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS health_records (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    fingerprint BLOB NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    UNIQUE (user_id, fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_batches (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    imported_count INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL,
                    skipped_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS health_records_user_id
                ON health_records (user_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS behavior_entries (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    fingerprint BLOB NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    UNIQUE (user_id, fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS behavior_entries_user_id
                ON behavior_entries (user_id)
                """
            )


def check_database(database_path: Path) -> None:
    """Raise a SQLite error if the initialized database is unavailable."""
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("Database schema metadata is missing.")
