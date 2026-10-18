"""동 리포트 응답. GET /api/dongs/{adm_cd}/report?category=cafe

    {
      "dong":      {"adm_cd": "1111053000", "name": "사직동", "gu": "종로구", "area_km2": 1.1649},  ← 어느 동
      "category":  {"code": "cafe", "name": "카페"},                                              ← 어떤 업종
      "base_date": "2026-09-30",                                                                ← 언제 기준
      "competition": {                                                                          ← 경쟁 축
        "open_count": 116,          사직동에 영업 중인 카페 116곳
        "density_per_km2": 99.6,    1km²당 99.6곳
        "gu_avg_density": 56.2,     종로구 행정동 평균은 56.2곳 → 구 평균의 약 1.8배
        "seoul_avg_density": 36.0,  서울 행정동 평균은 36.0곳
        "seoul_rank": 18,           서울 427개 동 중 18번째로 빽빽함 (상위 약 4%)
        "seoul_dong_count": 427
      },
      "stability": null, "site": null, "demand": null                                           ← 아직 데이터 없음
    }
"""
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.category import CategoryResponse
from app.schemas.dong import DongResponse


class ReportQuery(BaseModel):
    category: str = Field(description="업종 코드 cafe / bakery / korean", examples=["cafe"])


class CompareQuery(BaseModel):
    adm_cds: list[Annotated[str, StringConstraints(pattern=r"^\d{10}$")]] = Field(
        min_length=2,
        max_length=4,
        description="비교할 행정동 코드 2~4개",
        examples=[["1111053000", "1111054000"]],
    )
    category: str = Field(description="업종 코드 cafe / bakery / korean", examples=["cafe"])

    @field_validator("adm_cds")
    @classmethod
    def unique_dongs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("비교 행정동 코드는 중복될 수 없습니다.")
        return value


class CompetitionSection(BaseModel):
    """경쟁 축: "이 동네에 같은 업종 가게가 얼마나 빽빽한가".

    이 동의 값(open_count, density_per_km2)과 비교 기준(구 평균, 서울 평균, 순위)을 같이 준다.
    밀도가 평균보다 높을수록, 순위 숫자가 작을수록 경쟁이 심한 동네다.
    계산 방식은 app/services/report_service.py 의 _competition 참고.
    """

    open_count: int = Field(description="기준일에 영업 중인 이 업종 가게 수 (이 동 안)", examples=[116])
    density_per_km2: float = Field(description="1km²당 가게 수 = open_count ÷ 행정동 면적. 면적이 다른 동끼리 비교하는 값", examples=[99.6])
    gu_avg_density: float = Field(description="같은 구 행정동들의 밀도 평균 (동마다 1표인 단순 평균). 이 값보다 크면 구 안에서 빽빽한 편", examples=[56.2])
    seoul_avg_density: float = Field(description="서울 427개 행정동의 밀도 평균 (단순 평균)", examples=[36.0])
    seoul_rank: int = Field(description="서울 행정동 중 밀도 순위. 1 = 가장 빽빽함, 동점은 같은 순위", examples=[18])
    seoul_dong_count: int = Field(description="순위를 매긴 행정동 수. seoul_rank / seoul_dong_count 로 상위 몇 %인지 본다", examples=[427])


class DongReportResponse(BaseModel):
    """동 리포트: 한 행정동 × 한 업종에 대한 네 축(경쟁·안정성·자리·수요) 결과.

    축 값이 null이면 "아직 그 축 데이터가 없다"는 뜻이다 (0이나 나쁨이 아님). 화면은 '준비 중'으로 보여 준다.
    """

    dong: DongResponse = Field(description="요청한 행정동")
    category: CategoryResponse = Field(description="요청한 업종")
    base_date: date = Field(description="기준일. 모든 지표는 이 날 기준 (공통 규칙 2)", examples=["2026-09-30"])
    competition: CompetitionSection | None = Field(description="경쟁 축. 이 동·업종 데이터가 적재되지 않았으면 null")
    stability: "StabilitySection | None" = Field(description="3년 생존율·교체율·신규율. 값이 없으면 null")
    site: "SiteSection | None" = Field(description="행정동 내 자리 이력의 10년 기준 요약")
    demand: "DemandSection | None" = Field(description="시간대별 승하차·생활인구")


class StabilitySection(BaseModel):
    survival_3y: float | None = Field(description="3년 생존율 (0~1 비율, 구 단위 대체값일 수 있음)")
    turnover_rate: float | None = Field(description="최근 1년 교체율 (0~1 비율)")
    new_rate: float | None = Field(description="최근 1년 신규율 (0~1 비율)")
    turnover_basis: str = Field(description="교체율 기준: dong / gu / none")
    new_rate_basis: str = Field(description="신규율 기준: dong / gu / none")
    survival_basis: str = Field(description="생존율 기준: dong / gu / none")
    flow_type: str | None = Field(description="신규율·교체율 조합에 따른 설명 유형")
    cohort_3y: int = Field(description="3년 생존율 계산 대상 업소 수")
    new_1y: int = Field(description="최근 1년 신규 인허가 수")
    closed_1y: int = Field(description="최근 1년 폐업 수")


class SiteSection(BaseModel):
    site_count: int = Field(description="최근 10년 이력이 있는 행정동 내 주소 수")
    avg_single_permits_10y: float | None = Field(description="단독 점포 자리의 10년 평균 인허가 수")
    avg_per_slot_10y: float | None = Field(description="한 칸당 10년 평균 교체 횟수")


class DemandHour(BaseModel):
    hour: int
    subway_riders: float | None
    living_population: float | None


class StationDemand(BaseModel):
    station_name: str
    gu: str
    weekday_daily_riders: float
    weekend_daily_riders: float
    weekly_daily_riders: float
    weekend_weekday_ratio: float
    morning_alighting: float
    morning_boarding: float
    office_density: float
    evening_alighting: float
    night_boarding: float


class DemandSection(BaseModel):
    hourly: list[DemandHour]
    stations: list[StationDemand]


class DongComparisonResponse(BaseModel):
    category: CategoryResponse
    base_date: date
    items: list[DongReportResponse] = Field(description="점수나 종합 순위 없이 행정동별 리포트를 반환")
