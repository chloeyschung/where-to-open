from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Site


class SiteRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, site_id: int) -> Site | None:
        stmt = select(Site).options(selectinload(Site.stores)).where(Site.id == site_id)
        return self.db.scalars(stmt).first()

    def dong_summary(self, adm_cd: str) -> tuple[int, float | None, float | None]:
        count = self.db.scalar(select(func.count()).select_from(Site).where(Site.adm_cd == adm_cd)) or 0
        averages = self.db.execute(
            select(Site.dong_avg_single, Site.dong_avg_per_slot)
            .where(Site.adm_cd == adm_cd)
            .limit(1)
        ).first()
        if averages is None:
            return count, None, None
        return count, averages.dong_avg_single, averages.dong_avg_per_slot