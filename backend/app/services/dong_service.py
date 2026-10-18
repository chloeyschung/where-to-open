from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.dong_repo import DongRepository
from app.schemas.common import Page
from app.schemas.dong import DongListQuery, DongResponse


class DongService:
    def __init__(self, db: Session):
        self.dongs = DongRepository(db)

    def list_dongs(self, query: DongListQuery) -> Page[DongResponse]:
        items, total = self.dongs.search(gu=query.gu, q=query.q, offset=query.offset, limit=query.size)
        return Page[DongResponse](
            items=[DongResponse.model_validate(d) for d in items],
            total=total,
            page=query.page,
            size=query.size,
        )

    def get_dong(self, adm_cd: str) -> DongResponse:
        dong = self.dongs.get(adm_cd)
        if dong is None:
            raise NotFoundError(f"행정동 '{adm_cd}'이(가) 없습니다.")
        return DongResponse.model_validate(dong)

    def list_gu(self) -> list[str]:
        return self.dongs.list_gu()
