from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category

# 주석의 SQL은 SQL_ECHO=true 로 실제 Postgres에 찍힌 쿼리다. 바인드 값(%(x)s)은 예시 값으로 바꿔 적었다.
# 요청마다 BEGIN(첫 쿼리 때 자동) … COMMIT/ROLLBACK(get_db) 안에서 실행된다.


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Category]:
        #   SELECT category.code, category.name, category.sort_order FROM category ORDER BY category.sort_order
        return list(self.db.scalars(select(Category).order_by(Category.sort_order)))

    def get(self, code: str) -> Category | None:
        #   SELECT category.code, category.name, category.sort_order FROM category WHERE category.code = 'cafe'
        return self.db.get(Category, code)
