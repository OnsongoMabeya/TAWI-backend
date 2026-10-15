from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app import __version__
from app.config import get_settings
from app.db import init_db, shutdown_db
from app.routers import auth, users


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield
    await shutdown_db()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TAWI Backend",
        version=__version__,
        summary="Speech enhancement, transcription and account APIs for TAWI 2.0",
        lifespan=lifespan,
    )
    app.include_router(auth.router)
    app.include_router(users.router)

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        """Liveness probe used by CI, Docker and uptime checks."""
        return HealthResponse(
            status="ok",
            service="tawi-backend",
            version=__version__,
            environment=settings.environment,
        )

    return app


app = create_app()
