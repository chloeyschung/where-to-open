from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Dong

# 주석의 SQL은 SQL_ECHO=true 로 실제 Postgres에 찍힌 쿼리다. 바인드 값(%(x)s)은 예시 값으로 바꿔 적었다.
# 요청마다 BEGIN(첫 쿼리 때 자동) … COMMIT/ROLLBACK(get_db) 안에서 실행된다.


class DongRepository:
    def __init__(self, db: Session):
        self.db = db

    def search(self, *, gu: str | None, q: str | None, offset: int, limit: int) -> tuple[list[Dong], int]:
        stmt = select(Dong)
        if gu:
            stmt = stmt.where(Dong.gu == gu)
        if q:
            stmt = stmt.where(Dong.name.contains(q, autoescape=True))

        # GET /api/dongs?gu=종로구&q=사직&page=1&size=20 → 쿼리 2개
        # ① 전체 개수 (페이지와 무관). 같은 조건을 서브쿼리로 감싸 센다
        #   SELECT count(*) FROM (
        #     SELECT dong.* FROM dong
        #     WHERE dong.gu = '종로구' AND (dong.name LIKE '%' || '사직' || '%' ESCAPE '/')
        #   ) AS anon_1
        #   - contains(autoescape=True): 검색어 속 % _ 를 / 로 이스케이프해서 글자 그대로 찾는다
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        # ② 이번 페이지
        #   SELECT dong.adm_cd, dong.adm_cd8, dong.stat_cd, dong.name, dong.gu, dong.area_km2 FROM dong
        #   WHERE dong.gu = '종로구' AND (dong.name LIKE '%' || '사직' || '%' ESCAPE '/')
        #   ORDER BY dong.adm_cd LIMIT 20 OFFSET 0
        #   - gu·q가 없으면 WHERE 줄이 빠진다
        items = self.db.scalars(stmt.order_by(Dong.adm_cd).offset(offset).limit(limit))
        return list(items), total or 0

    def get(self, adm_cd: str) -> Dong | None:
        # 기본키 조회. 같은 세션에서 이미 읽은 동이면 SQL 없이 메모리(identity map)에서 꺼낸다
        #   SELECT dong.adm_cd, dong.adm_cd8, dong.stat_cd, dong.name, dong.gu, dong.area_km2
        #   FROM dong WHERE dong.adm_cd = '1111053000'

        return self.db.get(Dong, adm_cd)

    def list_gu(self) -> list[str]:
        #   SELECT DISTINCT dong.gu FROM dong ORDER BY dong.gu
        return list(self.db.scalars(select(Dong.gu).distinct().order_by(Dong.gu)))
