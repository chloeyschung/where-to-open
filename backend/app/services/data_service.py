from datetime import date, datetime

from sqlalchemy.orm import Session

from app.repositories.data_repo import DataRepository
from app.services.freshness import SCHEDULE, STAGES, current_base_date, demand_window, next_scheduled_run
from app.schemas.data import (
    DataOverviewResponse,
    DataPipelineResponse,
    BatchRunResponse,
    DataSourceResponse,
    MetricDefinitionResponse,
    PipelineStageResponse,
    RecordCountResponse,
)


# 데이터 출처. 데이터 분석 페이지(frontend-html/analysis/build_data.py)의 목록과 같게 유지한다.
# DB meta_source 표(3개만 적재됨) 대신 여기서 준다.
SOURCES = [
    ("permits-restaurant", "서울시 일반음식점 인허가 정보", "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do", "경쟁·안정성·자리", date(2026, 10, 13)),
    ("permits-cafe", "서울시 휴게음식점 인허가 정보", "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "https://data.seoul.go.kr/dataList/OA-16095/S/1/datasetView.do", "경쟁·안정성·자리", date(2026, 10, 13)),
    ("permits-bakery", "서울시 제과점영업 인허가 정보", "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "https://data.seoul.go.kr/dataList/OA-16084/S/1/datasetView.do", "경쟁·안정성·자리", date(2026, 10, 13)),
    ("subway-daily", "서울시 지하철호선별 역별 승하차 인원 정보 (일별)", "서울특별시",
     "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do", "수요", None),
    ("subway-hourly", "서울시 지하철 호선별 역별 시간대별 승하차 인원 정보", "서울특별시",
     "https://data.seoul.go.kr/dataList/OA-12252/S/1/datasetView.do", "수요", None),
    ("station-master", "서울시 역사마스터 정보 (역 좌표)", "서울특별시",
     "https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do", "수요", None),
    ("juso", "도로명주소 검색 API", "행정안전부", "https://business.juso.go.kr", "자리, 주소 검색", None),
    ("dong-boundaries", "행정동 경계 (admdongkor ver20260701)", "vuski/admdongkor (GitHub)",
     "https://github.com/vuski/admdongkor", "전체", None),
    ("sangga", "소상공인시장진흥공단 상가(상권)정보 (2026-06)", "소상공인시장진흥공단",
     "https://www.data.go.kr/data/15083033/fileData.do", "자리 (검증용)", None),
]


def _sources() -> list[DataSourceResponse]:
    return [DataSourceResponse(key=k, name=n, provider=p, url=u, axis=a, fetched_at=f) for k, n, p, u, a, f in SOURCES]


class DataService:
    def __init__(self, db: Session):
        self.db = db
        self.data = DataRepository(db)

    def overview(self) -> DataOverviewResponse:
        start, end = demand_window(self.db)
        return DataOverviewResponse(
            base_date=current_base_date(self.db),
            sources=_sources(),
            record_counts=[
                RecordCountResponse(dataset=label, table=table, records=count)
                for label, table, count in self.data.record_counts()
            ],
            metric_definitions=[
                MetricDefinitionResponse(axis="경쟁", metric="점포 밀도", definition="기준일 영업 중 점포 수 ÷ 행정동 면적"),
                MetricDefinitionResponse(axis="안정성", metric="3년 생존율", definition="3~8년 전 개업한 가게 중 3년 이상 영업했거나 아직 영업 중인 비율. 대상이 20곳 미만이면 구 값"),
                MetricDefinitionResponse(axis="안정성", metric="교체율·신규율", definition="최근 1년 폐업·신규 수를 1년 전 영업 중 가게 수로 나눈 비율. 1년 전 영업 중이 20곳 미만이면 구 값"),
                MetricDefinitionResponse(axis="자리", metric="10년 새 가게 수", definition="같은 지번(층·호 구분 없음)에 최근 10년 새로 들어온 가게 수. 주인만 바뀐 같은 상호는 한 가게로 셈"),
                MetricDefinitionResponse(axis="수요", metric="역별 승하차", definition=f"{start:%Y-%m}~{end:%Y-%m} 역별 평일·주말 하루 평균과 출퇴근·심야 지표"),
            ],
            score_policy="네 축을 하나의 종합 점수로 합산하거나 순위를 매기지 않습니다.",
        )

    def pipeline(self) -> DataPipelineResponse:
        last, ok = self.data.last_run(), self.data.last_success()
        keys = [k for k, _, _ in STAGES]

        def stage_status(key: str) -> str:
            if last is None:
                return "not_tracked"
            if last.status == "success":
                return "done"
            at = keys.index(last.stage) if last.stage in keys else -1
            here = keys.index(key)
            if here < at:
                return "done"
            if here == at:
                return {"running": "running", "failed": "failed"}.get(last.status, "not_run")
            return "not_run"

        def run(r):
            return None if r is None else BatchRunResponse.model_validate(r, from_attributes=True)

        return DataPipelineResponse(
            tracking_available=last is not None,
            stages=[
                PipelineStageResponse(key=k, name=n, description=d, status=stage_status(k),
                                      last_run_at=last.started_at if last else None)
                for k, n, d in STAGES
            ],
            sources=_sources(),
            base_date=current_base_date(self.db),
            schedule=SCHEDULE,
            next_run_at=next_scheduled_run(ok.base_date if ok else None),
            last_run=run(last),
            last_success=run(ok),
        )