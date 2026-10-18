from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    CompetitionStat,
    DemandStat,
    Dong,
    MetaSource,
    Site,
    SiteStore,
    StabilityAggregateStat,
    StabilityStat,
    Store,
    YearlyStat,
    StoreDong,
    SubwayStationStat,
    UptaeCount,
)


class DataRepository:
    def __init__(self, db: Session):
        self.db = db

    def sources(self) -> list[MetaSource]:
        return list(self.db.scalars(select(MetaSource).order_by(MetaSource.key)))

    def record_counts(self) -> list[tuple[str, str, int]]:
        datasets = [
            ("행정동", Dong),
            ("업종", Category),
            ("인허가 업소", Store),
            ("경쟁 통계", CompetitionStat),
            ("안정성 통계", StabilityStat),
            ("구·서울 안정성 기준", StabilityAggregateStat),
            ("연도별 신규·폐업", YearlyStat),
            ("자리", Site),
            ("자리 업소 이력", SiteStore),
            ("행정동 보충 매핑", StoreDong),
            ("원본 업태 건수", UptaeCount),
            ("시간대별 수요", DemandStat),
            ("역별 수요", SubwayStationStat),
        ]
        return [
            (
                label,
                model.__tablename__,
                self.db.scalar(select(func.count()).select_from(model)) or 0,
            )
            for label, model in datasets
        ]