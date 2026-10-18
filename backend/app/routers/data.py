from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.schemas.data import DataOverviewResponse, DataPipelineResponse
from app.services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["data"])


def get_service(db: DbSession) -> DataService:
    return DataService(db)


@router.get("/overview", response_model=DataOverviewResponse, summary="데이터 출처·건수·지표 정의")
def data_overview(service: Annotated[DataService, Depends(get_service)]):
    return service.overview()


@router.get("/pipeline", response_model=DataPipelineResponse, summary="수집·정규화 파이프라인 설명")
def data_pipeline(service: Annotated[DataService, Depends(get_service)]):
    return service.pipeline()