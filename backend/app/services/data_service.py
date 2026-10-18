from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.data_repo import DataRepository
from app.schemas.data import (
    DataOverviewResponse,
    DataPipelineResponse,
    DataSourceResponse,
    MetricDefinitionResponse,
    PipelineStageResponse,
    RecordCountResponse,
)


class DataService:
    def __init__(self, db: Session):
        self.data = DataRepository(db)

    def overview(self) -> DataOverviewResponse:
        return DataOverviewResponse(
            base_date=get_settings().base_date,
            sources=[DataSourceResponse.model_validate(source, from_attributes=True) for source in self.data.sources()],
            record_counts=[
                RecordCountResponse(dataset=label, table=table, records=count)
                for label, table, count in self.data.record_counts()
            ],
            metric_definitions=[
                MetricDefinitionResponse(axis="경쟁", metric="점포 밀도", definition="기준일 영업 중 점포 수 ÷ 행정동 면적"),
                MetricDefinitionResponse(axis="안정성", metric="3년 생존율", definition="개업 후 3년 이상 영업한 업소 비율"),
                MetricDefinitionResponse(axis="안정성", metric="교체율·신규율", definition="최근 1년 폐업·신규 수를 1년 전 영업 업소 수로 나눈 비율"),
                MetricDefinitionResponse(axis="자리", metric="10년 자리 이력", definition="같은 지번 주소의 최근 10년 인허가·폐업 이력"),
                MetricDefinitionResponse(axis="수요", metric="역별 승하차", definition="2024-09~2026-09 역별 평일·주말 하루 평균과 출퇴근·심야 지표"),
            ],
            score_policy="네 축을 하나의 종합 점수로 합산하거나 순위를 매기지 않습니다.",
        )

    def pipeline(self) -> DataPipelineResponse:
        stages = [
            ("collect", "수집", "공공데이터 원천에서 원본을 확보합니다."),
            ("normalize", "정규화", "행정동 코드와 주소 표기를 공통 기준으로 맞춥니다."),
            ("aggregate", "집계", "축별 지표와 시간대 통계를 사전 계산합니다."),
            ("load", "적재", "정제·집계 결과를 PostgreSQL 테이블에 반영합니다."),
        ]
        return DataPipelineResponse(
            tracking_available=False,
            stages=[
                PipelineStageResponse(key=key, name=name, description=description, status="not_tracked", last_run_at=None)
                for key, name, description in stages
            ],
            sources=[DataSourceResponse.model_validate(source, from_attributes=True) for source in self.data.sources()],
        )