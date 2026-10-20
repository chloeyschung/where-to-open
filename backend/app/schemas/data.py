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
    status: str = Field(description="최근 실행에서 이 단계의 결과: done / running / failed / not_run / not_tracked(기록 없음)")
    last_run_at: datetime | None = None


class BatchRunResponse(BaseModel):
    status: str = Field(description="running / success / failed / skipped")
    trigger: str = Field(description="schedule(매월 자동) / manual(수동 실행) / local")
    started_at: datetime
    finished_at: datetime | None
    base_date: date | None = Field(description="이 실행이 계산한 기준일")
    stage: str | None = Field(description="마지막으로 시작한 단계")
    message: str | None = Field(description="실패 이유 또는 요약")


class DataPipelineResponse(BaseModel):
    tracking_available: bool = Field(description="batch_run 기록을 읽을 수 있으면 true")
    stages: list[PipelineStageResponse]
    sources: list[DataSourceResponse]
    base_date: date = Field(description="지금 서비스 데이터의 기준일 (마지막 성공한 배치, 없으면 처음 적재한 기준일)")
    schedule: str = Field(description="갱신 일정")
    next_run_at: datetime = Field(description="다음 예약 실행 시각 (KST). 이번 달 갱신이 실패했으면 다음 날 09:00 (7일까지)")
    last_run: BatchRunResponse | None = Field(description="가장 최근 실행 (성공·실패 모두)")
    last_success: BatchRunResponse | None = Field(description="가장 최근 성공한 실행. 실패해도 서비스는 이 데이터를 계속 씀")