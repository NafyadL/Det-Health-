"""FastAPI application for the local Det(Health) prototype."""

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from app.database import check_database, initialize_database

DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "det_health.sqlite3"
)


def create_app(database_path: Path | str | None = None) -> FastAPI:
    """Create the app, optionally using a database path supplied by a test."""
    path = Path(
        database_path
        if database_path is not None
        else os.environ.get("DET_HEALTH_DB", DEFAULT_DATABASE_PATH)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(path)
        yield

    application = FastAPI(
        title="Det(Health)",
        description="Local-first health-data prototype.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        try:
            check_database(path)
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=503,
                detail="The local database is unavailable.",
            ) from exc
        return {"status": "ok", "storage": "sqlite"}

    return application


app = create_app()
