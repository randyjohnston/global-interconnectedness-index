"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gii.api.routes import agents, countries, index, pipelines

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Global Interconnectedness Index",
        description="Composite bilateral scores across trade, travel, and geopolitics",
        version="0.1.0",
    )

    # JSON API routes
    app.include_router(index.router)
    app.include_router(countries.router)
    app.include_router(pipelines.router)
    app.include_router(agents.router)

    # Dashboard static files
    static_dir = DASHBOARD_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Dashboard HTML routes (imported last to avoid route conflicts)
    from gii.dashboard.routes import router as dashboard_router
    app.include_router(dashboard_router)

    return app


app = create_app()
