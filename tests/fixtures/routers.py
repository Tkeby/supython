"""Small FastAPI router exposed for settings-module tests."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/fixture-test")
async def fixture_endpoint() -> dict[str, str]:
    return {"ok": "true"}
