from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Dong(Base):
    """서울 행정동 기준표 (competition/dong_area.csv, 427행)."""

    __tablename__ = "dong"

    adm_cd: Mapped[str] = mapped_column(String(10), primary_key=True, comment="행안부 행정동 코드 10자리")
    adm_cd8: Mapped[str] = mapped_column(String(8), unique=True, comment="앞 8자리, 생활인구 조인용")
    stat_cd: Mapped[str] = mapped_column(String(8), comment="통계청 행정동 코드")
    name: Mapped[str] = mapped_column(String(40))
    gu: Mapped[str] = mapped_column(String(20), index=True)
    area_km2: Mapped[float] = mapped_column(Float)



