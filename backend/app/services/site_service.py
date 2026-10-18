from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.site_repo import SiteRepository
from app.schemas.site import SiteDetailResponse
from app.services.category_service import CategoryService
from app.services.report_service import ReportService


class SiteService:
    def __init__(self, db: Session):
        self.db = db
        self.sites = SiteRepository(db)
        self.categories = CategoryService(db)

    def get_site(self, site_id: int, category_code: str) -> SiteDetailResponse:
        site = self.sites.get(site_id)
        if site is None:
            raise NotFoundError(f"자리 '{site_id}'가 없습니다.")
        category = self.categories.require(category_code)
        competition = None
        if site.adm_cd:
            competition = ReportService(self.db).dong_report(site.adm_cd, category.code).competition

        return SiteDetailResponse(
            id=site.id,
            site_key=site.site_key,
            gu=site.gu,
            adm_cd=site.adm_cd,
            category=category,
            permits_10y=site.permits_10y,
            max_concurrent=site.max_concurrent,
            per_slot_10y=site.per_slot_10y,
            closed_10y=site.closed_10y,
            avg_months_closed=site.avg_months_closed,
            open_now=site.open_now,
            open_now_names=site.open_now_names,
            dong_avg_single=site.dong_avg_single,
            dong_avg_per_slot=site.dong_avg_per_slot,
            dong_competition=competition,
            history=site.stores,
        )