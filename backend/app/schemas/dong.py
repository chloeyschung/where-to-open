from pydantic import Field

from app.schemas.common import ORMModel, PageQuery


class DongListQuery(PageQuery):
    gu: str | None = Field(None, description="자치구 이름", examples=["종로구"])
    q: str | None = Field(None, min_length=1, max_length=20, description="행정동 이름 부분 일치", examples=["사직"])


class DongResponse(ORMModel):
    """행정동 하나 (서울 427곳 중 하나). 다른 API는 adm_cd로 이 동을 가리킨다."""

    adm_cd: str = Field(description="행안부 행정동 코드 10자리. URL·다른 표와 이을 때 쓰는 키", examples=["1111053000"])
    name: str = Field(description="행정동 이름", examples=["사직동"])
    gu: str = Field(description="자치구 이름", examples=["종로구"])
    area_km2: float = Field(description="행정동 면적 (km²). 밀도 계산의 분모", examples=[1.1649])
