from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.site_repo import SiteRepository
from app.repositories.stat_repo import CompetitionRepository, StatRepository
from app.schemas.report import (
    CompetitionSection,
    DemandHour,
    DemandSection,
    DongComparisonResponse,
    DongReportResponse,
    SiteSection,
    StationDemand,
    StabilitySection,
)
from app.services.category_service import CategoryService
from app.services.dong_service import DongService


class ReportService:
    """한 동 × 한 업종의 네 축을 모은다. 지금은 경쟁 축만 채우고 나머지는 None."""

    def __init__(self, db: Session):
        self.dongs = DongService(db)
        self.categories = CategoryService(db)
        self.competition = CompetitionRepository(db)
        self.stats = StatRepository(db)
        self.sites = SiteRepository(db)

    def dong_report(self, adm_cd: str, category_code: str) -> DongReportResponse:
        dong = self.dongs.get_dong(adm_cd)  # 없으면 NotFoundError
        category = self.categories.require(category_code)
        return DongReportResponse(
            dong=dong,
            category=category,
            base_date=get_settings().base_date,
            competition=self._competition(adm_cd, dong.gu, category.code),
            stability=self._stability(adm_cd, category.code),
            site=self._site(adm_cd),
            demand=self._demand(adm_cd),
        )

    def compare_dongs(self, adm_cds: list[str], category_code: str) -> DongComparisonResponse:
        reports = [self.dong_report(adm_cd, category_code) for adm_cd in adm_cds]
        return DongComparisonResponse(
            category=reports[0].category,
            base_date=get_settings().base_date,
            items=reports,
        )

    def _stability(self, adm_cd: str, category_code: str) -> StabilitySection | None:
        stat = self.stats.get_stability(adm_cd, category_code)
        if stat is None:
            return None
        return StabilitySection(
            survival_3y=stat.display_survival_3y,
            turnover_rate=stat.display_turnover_rate,
            new_rate=stat.display_new_rate,
            turnover_basis=stat.turnover_basis,
            new_rate_basis=stat.new_rate_basis,
            survival_basis=stat.survival_basis,
            flow_type=stat.flow_type,
            cohort_3y=stat.cohort_3y,
            new_1y=stat.new_1y,
            closed_1y=stat.closed_1y,
        )

    def _site(self, adm_cd: str) -> SiteSection | None:
        count, avg_single, avg_per_slot = self.sites.dong_summary(adm_cd)
        if count == 0:
            return None
        return SiteSection(
            site_count=count,
            avg_single_permits_10y=avg_single,
            avg_per_slot_10y=avg_per_slot,
        )

    def _demand(self, adm_cd: str) -> DemandSection | None:
        hourly_rows = self.stats.demand_by_hour(adm_cd)
        station_rows = self.stats.subway_stations(adm_cd)
        if not hourly_rows and not station_rows:
            return None
        return DemandSection(
            hourly=[
                DemandHour(hour=row.hour, subway_riders=row.subway_riders, living_population=row.living_population)
                for row in hourly_rows
            ],
            stations=[StationDemand.model_validate(row, from_attributes=True) for row in station_rows],
        )

    def competition_only(self, adm_cd: str, category_code: str) -> CompetitionSection | None:
        """경쟁 축만 계산한다. 자리 상세처럼 동 리포트 전체가 필요 없을 때 쓴다."""
        dong = self.dongs.get_dong(adm_cd)  # 없으면 NotFoundError
        return self._competition(adm_cd, dong.gu, category_code)

    def _competition(self, adm_cd: str, gu: str, category_code: str) -> CompetitionSection | None:
        """경쟁 축. 이 동의 값은 DB(=CSV) 그대로, 비교 값만 여기서 계산한다.

          open_count, density_per_km2   competition_stat 그대로 (계산식은 scripts/load_data.py 의 load_competition)
          gu_avg_density                같은 구 행정동들의 밀도 단순 평균, 소수 1자리
          seoul_avg_density             서울 427개 행정동 밀도 단순 평균, 소수 1자리
          seoul_rank / seoul_dong_count 서울 행정동 중 밀도 순위 (동점은 같은 순위)

        평균·순위는 저장하지 않고 요청 때마다 계산한다. 데이터를 다시 적재해도 따로 갱신할 게 없다.

        리포트 한 번에 나가는 SQL 7개 (실제 순서, 한 트랜잭션):
          1. dong 기본키 조회              요청한 동                    (dong_repo.get)
          2. category 기본키 조회          요청한 업종                  (category_repo.get)
          3. competition_stat 기본키 조회  이 동·업종의 점포 수·밀도   (stat_repo.get)
          4. count(*) … density > 99.6     나보다 빽빽한 동 수          (stat_repo.rank_by_density)
          5. count(*)                      전체 동 수                   (stat_repo.rank_by_density)
          6. avg() … JOIN dong, gu = ?     구 평균                      (stat_repo.avg_density)
          7. avg()                         서울 평균                    (stat_repo.avg_density)
        각 SQL 원문은 repositories/ 의 해당 메서드 주석에 있다.
        """
        stat = self.competition.get(adm_cd, category_code)
        if stat is None:
            return None
        rank, total = self.competition.rank_by_density(category_code, stat.density_per_km2)
        return CompetitionSection(
            open_count=stat.open_count,
            density_per_km2=stat.density_per_km2,
            gu_avg_density=round(self.competition.avg_density(category_code, gu), 1),
            seoul_avg_density=round(self.competition.avg_density(category_code), 1),
            seoul_rank=rank,
            seoul_dong_count=total,
        )
