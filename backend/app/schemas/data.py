from datetime import date, datetime

from pydantic import BaseModel, Field


class DataSourceResponse(BaseModel):
    key: str
    name: str
    provider: str
    url: str
    axis: str
    fetched_at: date | None = Field(description="원천 데이터 다운로드 날짜")


class RecordCountResponse(BaseModel):
    dataset: str
    table: str
    records: int


class MetricDefinitionResponse(BaseModel):
    axis: str
    metric: str
    definition: str


class DataOverviewResponse(BaseModel):
    base_date: date
    sources: list[DataSourceResponse]
    record_counts: list[RecordCountResponse]
    metric_definitions: list[MetricDefinitionResponse]
    score_policy: str = Field(description="종합 점수를 만들지 않는다는 정책")


class PipelineStageResponse(BaseModel):
    key: str
    name: str
    description: str
    status: str = Field(description="현재 백엔드에는 실행 로그가 없어 not_tracked")
    last_run_at: datetime | None = None


class DataPipelineResponse(BaseModel):
    tracking_available: bool
    stages: list[PipelineStageResponse]
    sources: list[DataSourceResponse]