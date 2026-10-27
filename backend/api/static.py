"""Serve built React frontend as static files from FastAPI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Built frontend: project_root/frontend/dist/
_ROOT = Path(__file__).parent.parent.parent
FRONTEND_DIST = _ROOT / "frontend" / "dist"


def mount_static(app: FastAPI) -> None:
    """Mount React build as static files.

    Call this AFTER registering all /api/* routes so the SPA catch-all
    doesn't intercept API 404s.

    Only active in production (inside Docker). Local dev uses Vite on :5173.
    """
    if not FRONTEND_DIST.exists():
        return

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        return FileResponse(str(FRONTEND_DIST / "index.html"))
