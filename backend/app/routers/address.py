from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.schemas.address import AddressSearchResponse
from app.schemas.common import ErrorResponse
from app.services.address_service import AddressService

router = APIRouter(prefix="/api/address", tags=["address"])


def get_service(db: DbSession) -> AddressService:
    return AddressService(db)


@router.get(
    "/search",
    response_model=AddressSearchResponse,
    responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="주소 검색 → 자리·행정동 (도로명주소 API 실시간 호출)",
)
def search_address(
    q: Annotated[str, Query(min_length=2, max_length=80, description="지번 또는 도로명 주소", examples=["황학동 479"])],
    service: Annotated[AddressService, Depends(get_service)],
):
    return service.search(q)
