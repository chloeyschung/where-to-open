from fastapi import APIRouter

from app.core.database import check_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="앱·DB 상태 확인")
def health() -> HealthResponse:
    return HealthResponse(status="ok", db="ok" if check_db() else "unavailable")
