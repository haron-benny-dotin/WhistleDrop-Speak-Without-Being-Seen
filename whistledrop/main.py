import logging
import sqlite3
from typing import Optional

from fastapi import FastAPI, Request

from . import store
from .config import Settings, load_settings
from .db import connect, init_db
from .errors import register_error_handlers
from .routes_moderator import router as moderator_router
from .routes_public import router as public_router

log = logging.getLogger("whistledrop")

DESCRIPTION = """
Confidential reporting backend. Anyone can submit a report without an account and
track it with a secret case code. Moderators review and update reports but can never
see who submitted them.

**Moderators:** call `POST /moderator/login`, then click **Authorize** and paste the token.
"""


def _bootstrap_moderator(settings: Settings) -> None:
    if not (settings.bootstrap_username and settings.bootstrap_password):
        return
    conn = connect(settings.database_path)
    try:
        if store.moderator_by_username(conn, settings.bootstrap_username) is None:
            try:
                store.create_moderator(conn, settings.bootstrap_username,
                                       settings.bootstrap_password)
                log.info("Created bootstrap moderator account.")
            except sqlite3.IntegrityError:
                # another worker already created it
                pass
    finally:
        conn.close()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    init_db(settings.database_path)
    _bootstrap_moderator(settings)

    app = FastAPI(title="WhistleDrop API", version="1.0.0", description=DESCRIPTION)
    app.state.settings = settings
    register_error_handlers(app)

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        # don't let browsers/proxies cache anything
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(public_router)
    app.include_router(moderator_router)

    @app.get("/health", tags=["Meta"], summary="Is the service up?")
    def health():
        return {"status": "ok"}

    return app
