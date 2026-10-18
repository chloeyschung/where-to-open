from pydantic import Field

from app.schemas.common import ORMModel


class CategoryResponse(ORMModel):
    """업종 하나. 지금은 카페·제과점·한식 3개로 고정 (공통 규칙 3)."""

    code: str = Field(description="업종 코드. 다른 API의 category 값으로 쓴다 (cafe / bakery / korean)", examples=["cafe"])
    name: str = Field(description="화면에 보이는 업종 이름", examples=["카페"])
