from pydantic import BaseModel, Field


class AddressMatch(BaseModel):
    jibun_addr: str = Field(description="도로명주소 API가 돌려준 지번 주소", examples=["서울특별시 중구 황학동 479"])
    road_addr: str = Field(description="도로명주소", examples=["서울특별시 중구 퇴계로87길 49-16 (황학동)"])
    building: str | None = Field(description="건물 이름. 없으면 null")
    site_key: str | None = Field(description="자리 키(구 동 번지). 번지를 모르면 null", examples=["중구 황학동 479"])
    site_id: int | None = Field(description="자리 id. 최근 10년 가게 기록이 없는 주소면 null → /api/sites/{site_id}")
    permits_10y: int | None = Field(description="그 자리의 최근 10년 새로 들어온 가게 수. 자리가 없으면 null")
    gu: str = Field(examples=["중구"])
    adm_cd: str | None = Field(description="행정동 코드 10자리. 못 찾으면 null", examples=["1114067000"])
    dong: str | None = Field(description="행정동 이름", examples=["황학동"])
    dong_basis: str | None = Field(
        description="행정동을 정한 근거. site = 자리 데이터(가게 좌표 기준, 다른 축과 같은 값), "
        "juso = 도로명주소 API의 행정동 이름, null = 못 찾음",
        examples=["site"],
    )


class AddressSearchResponse(BaseModel):
    query: str = Field(examples=["황학동 479"])
    total: int = Field(description="도로명주소 API가 찾은 주소(건물) 수. 서울 밖 포함, 같은 지번의 건물도 따로 셈")
    truncated: bool = Field(description="찾은 주소가 한 번에 받는 수(20)보다 많아 뒤쪽을 받지 않았으면 true. 주소를 더 자세히 넣으면 좁혀진다")
    items: list[AddressMatch]
