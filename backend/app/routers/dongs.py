from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.database import DbSession
from app.schemas.common import ErrorResponse, Page
from app.schemas.dong import DongListQuery, DongResponse
from app.services.dong_service import DongService

router = APIRouter(prefix="/api/dongs", tags=["dongs"])

AdmCd = Annotated[str, Path(pattern=r"^\d{10}$", description="행정동 코드 10자리", examples=["1111053000"])]


def get_service(db: DbSession) -> DongService:
    return DongService(db)


@router.get("", response_model=Page[DongResponse], summary="행정동 목록·검색")
def list_dongs(
    query: Annotated[DongListQuery, Query()],
    service: Annotated[DongService, Depends(get_service)],
):
    return service.list_dongs(query)


@router.get("/gu", response_model=list[str], summary="자치구 목록")
def list_gu(service: Annotated[DongService, Depends(get_service)]):
    return service.list_gu()


@router.get(
    "/{adm_cd}",
    response_model=DongResponse,
    responses={404: {"model": ErrorResponse}},
    summary="행정동 기본 정보",
)
def get_dong(adm_cd: AdmCd, service: Annotated[DongService, Depends(get_service)]):
    return service.get_dong(adm_cd)
