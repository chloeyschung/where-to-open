"""월 배치 실행 기록 (batch/run.py → backend/batch_load.py 가 쓴다)."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BatchRun(Base):
    __tablename__ = "batch_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), comment="running / success / failed / skipped")
    trigger: Mapped[str] = mapped_column(String(20), comment="schedule / manual / local")
    stage: Mapped[str | None] = mapped_column(String(40), comment="마지막으로 시작한 단계")
    base_date: Mapped[date | None] = mapped_column(Date, comment="이 실행이 계산한 기준일")
    demand_start: Mapped[date | None] = mapped_column(Date, comment="수요 기간 시작")
    demand_end: Mapped[date | None] = mapped_column(Date, comment="수요 기간 끝")
    message: Mapped[str | None] = mapped_column(Text, comment="실패 이유 또는 요약")
    row_counts: Mapped[str | None] = mapped_column(Text, comment="적재한 표별 행 수 (JSON)")
