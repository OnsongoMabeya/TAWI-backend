from fastapi import FastAPI
from pydantic import BaseModel

from app import __version__
from app.config import get_settings


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
    )

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
