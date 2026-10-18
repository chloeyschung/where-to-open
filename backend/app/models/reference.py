"""축별 스크립트가 만든 보조 CSV. 지표 계산에는 쓰지 않고 확인·설명용으로 둔다."""
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StoreDong(Base):
    """자리 축 (jari/dong_fill.csv). 공용 파일에서 행정동이 비어 있던 업소를 주소 조회로 채운 결과."""

    __tablename__ = "store_dong"

    source: Mapped[str] = mapped_column(String(20), primary_key=True, comment="cafe / bakery / restaurant")
    mgt_no: Mapped[str] = mapped_column(String(40), primary_key=True)
    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), index=True)
    adm_nm: Mapped[str] = mapped_column(String(40))
    gu: Mapped[str] = mapped_column(String(20))
    via: Mapped[str] = mapped_column(String(10), comment="jibun 지번 / road 도로명주소로 찾음")
    is_open: Mapped[bool] = mapped_column(Boolean)


class UptaeCount(Base):
    """경쟁 축 (competition/uptae_counts.csv). 인허가 원본 파일별 업태 분포."""

    __tablename__ = "uptae_count"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True, comment="cafe / bakery / restaurant")
    uptae: Mapped[str | None] = mapped_column(String(50), comment="원본에 업태가 빈 업소는 NULL")
    count: Mapped[int] = mapped_column(Integer)


class CategoryKeyword(Base):
    """안정성 축 (stability/category_map.csv). 상호·업태 키워드 → 세부 업종."""

    __tablename__ = "category_keyword"

    keyword: Mapped[str] = mapped_column(String(40), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), comment="제외면 집계에서 뺀다")
