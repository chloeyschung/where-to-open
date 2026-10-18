from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.schemas.category import CategoryResponse
from app.services.category_service import CategoryService

router = APIRouter(prefix="/api/categories", tags=["categories"])


def get_service(db: DbSession) -> CategoryService:
    return CategoryService(db)


@router.get("", response_model=list[CategoryResponse], summary="업종 목록 (카페·제과점·한식)")
def list_categories(service: Annotated[CategoryService, Depends(get_service)]):
    return service.list_categories()
