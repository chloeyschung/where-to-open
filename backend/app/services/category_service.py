from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryResponse


class CategoryService:
    def __init__(self, db: Session):
        self.categories = CategoryRepository(db)

    def list_categories(self) -> list[CategoryResponse]:
        return [CategoryResponse.model_validate(c) for c in self.categories.list_all()]

    def require(self, code: str) -> CategoryResponse:
        """다른 Service가 업종 코드를 검증할 때 쓴다."""
        category = self.categories.get(code)
        if category is None:
            raise NotFoundError(f"업종 '{code}'이(가) 없습니다.")
        return CategoryResponse.model_validate(category)
