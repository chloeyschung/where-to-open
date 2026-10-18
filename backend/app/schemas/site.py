from datetime import date

from pydantic import Field

from app.schemas.category import CategoryResponse
from app.schemas.common import ORMModel
from app.schemas.report import CompetitionSection


class SiteHistoryResponse(ORMModel):
    mgt_nos: str = Field(description="합쳐진 인허가 관리번호")
    name: str
    kind: str
    uptae: str | None
    open_date: date
    close_date: date | None
    months: float | None = Field(description="기준일까지 계산한 영업 개월")
    merged: int


class SiteDetailResponse(ORMModel):
    id: int
    site_key: str = Field(description="구·동·번지 주소 키. 층·호는 구분하지 않음")
    gu: str
    adm_cd: str | None
    category: CategoryResponse
    permits_10y: int
    max_concurrent: int
    per_slot_10y: float
    closed_10y: int
    avg_months_closed: float | None
    open_now: int
    open_now_names: str | None
    dong_avg_single: float | None
    dong_avg_per_slot: float | None
    dong_competition: CompetitionSection | None = Field(description="선택 업종의 행정동 밀도 비교. 반경 내 밀도는 아님")
    history: list[SiteHistoryResponse]