from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.database import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.site import SiteDetailResponse
from app.services.site_service import SiteService

router = APIRouter(prefix="/api/sites", tags=["sites"])


def get_service(db: DbSession) -> SiteService:
    return SiteService(db)


@router.get(
    "/{site_id}",
    response_model=SiteDetailResponse,
    responses={404: {"model": ErrorResponse}},
    summary="자리의 10년 지표·업소 이력",
)
def get_site(
    site_id: Annotated[int, Path(description="자리 id. 주소 검색(/api/address/search) 결과의 site_id")],
    category: Annotated[str, Query(description="업종 코드 cafe / bakery / korean")],
    service: Annotated[SiteService, Depends(get_service)],
):
    return service.get_site(site_id, category)