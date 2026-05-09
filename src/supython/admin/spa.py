import logging
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def mount(app: FastAPI) -> None:
    static_dir = Path(str(files("supython.admin").joinpath("static")))
    assets_path = static_dir / "assets"
    index = static_dir / "index.html"

    if assets_path.exists():
        app.mount(
            "/admin/assets",
            StaticFiles(directory=assets_path),
            name="admin-assets",
        )

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = "") -> FileResponse:
        if not index.exists():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin SPA bundle not built. Run `npm run build` in admin-ui/.",
            )
        return FileResponse(index)

    if not index.exists():
        logger.warning(
            "Admin SPA index.html not found at %s — /admin will return 503 until the bundle is built.",
            index,
        )
