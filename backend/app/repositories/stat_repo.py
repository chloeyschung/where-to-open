from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CompetitionStat, DemandStat, Dong, StabilityStat, SubwayStationStat

# 주석의 SQL은 SQL_ECHO=true 로 실제 Postgres에 찍힌 쿼리다. 바인드 값(%(x)s)은 예시 값으로 바꿔 적었다.
# 요청마다 BEGIN(첫 쿼리 때 자동) … COMMIT/ROLLBACK(get_db) 안에서 실행된다.


class CompetitionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, adm_cd: str, category_code: str) -> CompetitionStat | None:
        # 복합 기본키 (adm_cd, category_code) 조회
        #   SELECT competition_stat.adm_cd, competition_stat.category_code,
        #          competition_stat.open_count, competition_stat.density_per_km2
        #   FROM competition_stat
        #   WHERE competition_stat.adm_cd = '1111053000' AND competition_stat.category_code = 'cafe'
        return self.db.get(CompetitionStat, (adm_cd, category_code))

    def avg_density(self, category_code: str, gu: str | None = None) -> float:
        """행정동 밀도의 단순 평균. gu를 주면 그 구의 행정동만, 안 주면 서울 전체 427곳.

        동마다 가중치 1인 평균이다 (= 동 밀도들을 더해서 동 개수로 나눔).
        "구 전체 가게 수 ÷ 구 전체 면적"과는 다르다. 면적이 큰 동 하나가 평균을 좌우하지 않고
        "보통 동네 하나와 비교하면 어떤가"를 보여 주려는 값이다. 가게가 0인 동도 0으로 포함된다.
        """
        # 서울 평균 (gu 없음)
        #   SELECT avg(competition_stat.density_per_km2) FROM competition_stat
        #   WHERE competition_stat.category_code = 'cafe'                                → 36.0
        # 구 평균 (gu 있음). 구 이름은 dong 표에 있어서 JOIN 한다
        #   SELECT avg(competition_stat.density_per_km2)
        #   FROM competition_stat JOIN dong ON dong.adm_cd = competition_stat.adm_cd
        #   WHERE competition_stat.category_code = 'cafe' AND dong.gu = '종로구'         → 56.2
        stmt = select(func.avg(CompetitionStat.density_per_km2)).where(CompetitionStat.category_code == category_code)
        if gu:
            stmt = stmt.join(Dong, Dong.adm_cd == CompetitionStat.adm_cd).where(Dong.gu == gu)
        return float(self.db.scalar(stmt) or 0.0)

    def rank_by_density(self, category_code: str, density: float) -> tuple[int, int]:
        """(순위, 전체 수). 순위 = 밀도가 더 높은 동의 수 + 1 (1위 = 가장 빽빽함).

        밀도가 같은 동은 같은 순위를 받고 다음 순위는 그만큼 건너뛴다 (예: 3위 둘 → 다음은 5위).
        전체 수는 그 업종 행이 있는 행정동 수 (지금은 서울 427곳 전부, 가게 0인 동 포함).
        """
        base = select(func.count()).select_from(CompetitionStat).where(CompetitionStat.category_code == category_code)
        # ① 나보다 밀도가 높은 동의 수 (사직동 카페 99.6 → 17곳 → 18위)
        #   SELECT count(*) FROM competition_stat
        #   WHERE competition_stat.category_code = 'cafe' AND competition_stat.density_per_km2 > 99.6
        higher = self.db.scalar(base.where(CompetitionStat.density_per_km2 > density)) or 0
        # ② 전체 동 수 (427)
        #   SELECT count(*) FROM competition_stat WHERE competition_stat.category_code = 'cafe'
        total = self.db.scalar(base) or 0
        return higher + 1, total


class StatRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_stability(self, adm_cd: str, category_code: str) -> StabilityStat | None:
        return self.db.get(StabilityStat, (adm_cd, category_code))

    def demand_by_hour(self, adm_cd: str) -> list[DemandStat]:
        stmt = select(DemandStat).where(DemandStat.adm_cd == adm_cd).order_by(DemandStat.hour)
        return list(self.db.scalars(stmt))

    def subway_stations(self, adm_cd: str) -> list[SubwayStationStat]:
        stmt = (
            select(SubwayStationStat)
            .where(SubwayStationStat.adm_cd == adm_cd)
            .order_by(SubwayStationStat.weekly_daily_riders.desc(), SubwayStationStat.station_name)
        )
        return list(self.db.scalars(stmt))
