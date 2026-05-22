from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from glass.db import close_pool


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_pool()


def create_app() -> FastAPI:
    from glass.config import settings

    app = FastAPI(title="Glass Sidebar", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from glass.api.ask import router as ask_router
    from glass.api.cards import router as cards_router
    from glass.api.sessions import router as sessions_router
    from glass.api.setup import router as setup_router
    from glass.api.ws_audio import router as ws_audio_router
    from glass.api.ws_dashboard import router as ws_dashboard_router

    app.include_router(sessions_router, prefix="/api")
    app.include_router(cards_router, prefix="/api")
    app.include_router(setup_router, prefix="/api")
    app.include_router(ask_router, prefix="/api")
    app.include_router(ws_audio_router)
    app.include_router(ws_dashboard_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Production entry point lives in glass/api/main.py: uvicorn glass.api.main:app
# This module only exports create_app() so tests can call it after monkeypatching.
