from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Store(Base):
    """공용 파일 permits_base.csv 중 카페·제과점·한식. 예비 표 (지금은 적재하지 않음)."""

    __tablename__ = "store"
    __table_args__ = (Index("ix_store_category_open_latlon", "category_code", "is_open_asof", "lat", "lon"),)

    # 관리번호는 원본 파일 안에서만 고유해서 source와 묶어 키로 쓴다
    source: Mapped[str] = mapped_column(String(20), primary_key=True, comment="cafe / bakery / restaurant")
    mgt_no: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    uptae: Mapped[str | None] = mapped_column(String(50))
    category_code: Mapped[str] = mapped_column(ForeignKey("category.code"))
    permit_date: Mapped[date] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    jibun_addr: Mapped[str | None] = mapped_column(String(300))
    road_addr: Mapped[str | None] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    adm_cd: Mapped[str | None] = mapped_column(ForeignKey("dong.adm_cd"), index=True)
    is_temp: Mapped[bool] = mapped_column(Boolean, default=False, comment="팝업·행사 (공통 규칙 5)")
    close_date_missing: Mapped[bool] = mapped_column(Boolean, default=False, comment="공통 규칙 4")
    is_open_asof: Mapped[bool] = mapped_column(Boolean, comment="기준일 영업 중 (공통 규칙 2, 적재 때 계산)")
