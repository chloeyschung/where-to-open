from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Category(Base):
    """업종 3개 고정 (공통 규칙 3): cafe 카페, bakery 제과점, korean 한식."""

    __tablename__ = "category"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
