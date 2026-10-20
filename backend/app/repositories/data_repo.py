from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    BatchRun,
    Category,
    CompetitionStat,
    DemandStat,
    Dong,
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

    def _first_run(self, stmt) -> BatchRun | None:
        # batch_run 표가 아직 없거나 조회가 실패해도 다른 API가 멈추지 않게, SAVEPOINT 안에서 읽고 실패하면 None
        try:
            with self.db.begin_nested():
                return self.db.scalars(stmt).first()
        except SQLAlchemyError:
            return None

    def last_run(self) -> BatchRun | None:
        #   SELECT ... FROM batch_run ORDER BY started_at DESC LIMIT 1
        return self._first_run(select(BatchRun).order_by(BatchRun.started_at.desc()).limit(1))

    def last_success(self) -> BatchRun | None:
        #   SELECT ... FROM batch_run WHERE status = 'success' ORDER BY finished_at DESC LIMIT 1
        return self._first_run(
            select(BatchRun).where(BatchRun.status == "success").order_by(BatchRun.finished_at.desc()).limit(1)
        )

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