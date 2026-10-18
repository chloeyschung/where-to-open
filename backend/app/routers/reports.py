from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.routers.dongs import AdmCd
from app.schemas.common import ErrorResponse
from app.schemas.report import CompareQuery, DongComparisonResponse, DongReportResponse, ReportQuery
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/dongs", tags=["reports"])


def get_service(db: DbSession) -> ReportService:
    return ReportService(db)


@router.get(
    "/{adm_cd}/report",
    response_model=DongReportResponse,
    responses={404: {"model": ErrorResponse}},
    summary="한 동 × 한 업종의 네 축 리포트",
)
def dong_report(
    adm_cd: AdmCd,
    query: Annotated[ReportQuery, Query()],
    service: Annotated[ReportService, Depends(get_service)],
):
    return service.dong_report(adm_cd, query.category)


@router.get("/compare", response_model=DongComparisonResponse, summary="2~4개 행정동의 네 축 비교")
def compare_dongs(
    query: Annotated[CompareQuery, Query()],
    service: Annotated[ReportService, Depends(get_service)],
):
    return service.compare_dongs(query.adm_cds, query.category)
