"""자리 축 (jari/sites.py 결과). 자리 = 같은 지번, 층·호는 구분하지 않는다."""
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Site(Base):
    __tablename__ = "site"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_key: Mapped[str] = mapped_column(String(100), unique=True, comment="구 동 번지 (URL에는 id 사용)")
    gu: Mapped[str] = mapped_column(String(20), index=True)
    adm_cd: Mapped[str | None] = mapped_column(ForeignKey("dong.adm_cd"), index=True)
    permits_10y: Mapped[int] = mapped_column(Integer, comment="최근 10년 새로 들어온 가게 수")
    max_concurrent: Mapped[int] = mapped_column(Integer, comment="최근 10년 최대 동시 영업 수")
    per_slot_10y: Mapped[float] = mapped_column(Float)
    closed_10y: Mapped[int] = mapped_column(Integer)
    avg_months_closed: Mapped[float | None] = mapped_column(Float)
    open_now: Mapped[int] = mapped_column(Integer)
    open_now_names: Mapped[str | None] = mapped_column(Text)
    dong_avg_single: Mapped[float | None] = mapped_column(Float)
    dong_avg_per_slot: Mapped[float | None] = mapped_column(Float)

    stores: Mapped[list["SiteStore"]] = relationship(back_populates="site", order_by="SiteStore.open_date")


class SiteStore(Base):
    """자리의 가게 이력 (site_history.csv). 주인만 바뀐 가게는 합쳐져 mgt_nos가 여러 개일 수 있다."""

    __tablename__ = "site_store"
    __table_args__ = (UniqueConstraint("site_id", "mgt_nos", name="uq_site_store_site_id_mgt_nos"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id", ondelete="CASCADE"), index=True)
    mgt_nos: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), comment="원천 유형: restaurant / cafe / bakery")
    uptae: Mapped[str | None] = mapped_column(String(50))
    open_date: Mapped[date] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    months: Mapped[float | None] = mapped_column(Float)
    merged: Mapped[int] = mapped_column(Integer, default=0, comment="같은 가게로 합쳐진 인허가 수")

    site: Mapped[Site] = relationship(back_populates="stores")
