from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """ORM 객체에서 바로 만들 수 있는 응답 DTO의 기본형."""

    model_config = ConfigDict(from_attributes=True)


class PageQuery(BaseModel):
    page: int = Field(1, ge=1, description="1부터 시작")
    size: int = Field(20, ge=1, le=100, description="한 페이지 개수")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page[T](BaseModel):
    """목록 응답의 공통 모양. items는 이번 페이지 것만, total은 조건에 맞는 전체 개수.

    마지막 페이지 번호 = ceil(total / size). items가 size보다 적으면 마지막 페이지다.
    """

    items: list[T] = Field(description="이번 페이지에 담긴 항목")
    total: int = Field(description="검색 조건에 맞는 전체 개수 (페이지와 무관)", examples=[427])
    page: int = Field(description="요청한 페이지 번호 (1부터)", examples=[1])
    size: int = Field(description="한 페이지 최대 개수", examples=[20])


class ErrorBody(BaseModel):
    code: str = Field(
        description="에러 종류. 프론트가 분기할 때 쓴다 "
        "(NOT_FOUND, VALIDATION_ERROR, HTTP_ERROR, INTERNAL_ERROR, TX_TEST_FAILED 등)",
        examples=["NOT_FOUND"],
    )
    message: str = Field(description="사용자에게 그대로 보여 줘도 되는 한국어 문장", examples=["행정동 '9999999999'이(가) 없습니다."])
    details: object | None = Field(None, description="추가 정보. 검증 실패면 어느 값이 왜 틀렸는지 목록, 없으면 생략")


class ErrorResponse(BaseModel):
    """모든 에러 응답의 모양 (app/core/exceptions.py). 상태 코드와 상관없이 항상 error 안에 담긴다."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """서버 상태. 화면 오른쪽 위 연결 표시가 이 값을 쓴다."""

    status: str = Field(description="앱 상태. 응답이 왔다면 항상 ok (앱이 꺼져 있으면 응답 자체가 없다)", examples=["ok"])
    db: str = Field(description="DB 연결. SELECT 1이 성공하면 ok, 실패하면 unavailable", examples=["ok"])
