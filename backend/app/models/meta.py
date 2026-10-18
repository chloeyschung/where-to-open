from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetaSource(Base):
    """데이터 출처 (과제 요건: 명칭, 제공 기관, URL)."""

    __tablename__ = "meta_source"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(300))
    axis: Mapped[str] = mapped_column(String(40), comment="쓰는 축")
    fetched_at: Mapped[date | None] = mapped_column(Date, comment="내려받은 날")
