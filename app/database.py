"""SQLite initialization and readiness checks."""

import sqlite3
from contextlib import closing
from pathlib import Path


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
                VALUES ('schema_version', '1')
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
