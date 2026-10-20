"""행정동 × 업종 단위로 축별 스크립트가 미리 계산한 지표. 백엔드는 다시 계산하지 않는다."""
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompetitionStat(Base):
    """경쟁 축 (competition/competition_by_dong.csv를 업종별 행으로 펼침)."""

    __tablename__ = "competition_stat"

    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("category.code"), primary_key=True)
    open_count: Mapped[int] = mapped_column(Integer, comment="기준일 영업 중 점포 수")
    density_per_km2: Mapped[float] = mapped_column(Float, comment="점포 수 ÷ 행정동 면적")


class StabilityStat(Base):
    """안정성 축 (stability/data/stability_by_dong.csv). 화면·API는 display_* 값을 쓴다."""

    __tablename__ = "stability_stat"

    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("category.code"), primary_key=True)
    open_base: Mapped[int] = mapped_column(Integer, comment="기준일 1년 전 영업 중")
    open_now: Mapped[int] = mapped_column(Integer, comment="기준일 영업 중")
    new_1y: Mapped[int] = mapped_column(Integer)
    closed_1y: Mapped[int] = mapped_column(Integer)
    turnover_rate: Mapped[float | None] = mapped_column(Float, comment="폐업_1년 ÷ 영업중_기초, 표본 부족이면 NULL")
    new_rate: Mapped[float | None] = mapped_column(Float)
    cohort_3y: Mapped[int] = mapped_column(Integer, comment="기준일 8~3년 전 개업 수")
    survival_3y: Mapped[float | None] = mapped_column(Float)
    display_turnover_rate: Mapped[float | None] = mapped_column(Float, comment="동 값이 없으면 구 값")
    display_new_rate: Mapped[float | None] = mapped_column(Float)
    display_survival_3y: Mapped[float | None] = mapped_column(Float)
    turnover_basis: Mapped[str] = mapped_column(String(10), comment="교체율 기준: dong / gu / none")
    new_rate_basis: Mapped[str] = mapped_column(String(10), comment="신규율 기준: dong / gu / none")
    survival_basis: Mapped[str] = mapped_column(String(10), comment="생존율 기준: dong / gu / none")
    flow_type: Mapped[str | None] = mapped_column(String(20), comment="신규율·교체율 4분면, 설명용")


class StabilityAggregateStat(Base):
    """구·서울 단위 안정성 비교 기준 (stability_by_gu.csv, stability_seoul.csv)."""

    __tablename__ = "stability_aggregate_stat"

    scope: Mapped[str] = mapped_column(String(10), primary_key=True, comment="gu / seoul")
    area_name: Mapped[str] = mapped_column(String(20), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("category.code"), primary_key=True)
    base_date: Mapped[date] = mapped_column(Date)
    open_base: Mapped[int] = mapped_column(Integer)
    open_now: Mapped[int] = mapped_column(Integer)
    new_1y: Mapped[int] = mapped_column(Integer)
    closed_1y: Mapped[int] = mapped_column(Integer)
    cohort_3y: Mapped[int] = mapped_column(Integer)
    survived_3y: Mapped[int] = mapped_column(Integer)
    turnover_rate: Mapped[float | None] = mapped_column(Float)
    new_rate: Mapped[float | None] = mapped_column(Float)
    survival_rate: Mapped[float | None] = mapped_column(Float)


class YearlyStat(Base):
    """연도별 신규·폐업 (stability/out/yearly_by_dong.csv). 예비 표 (지금은 적재하지 않음)."""

    __tablename__ = "yearly_stat"

    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("category.code"), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_count: Mapped[int] = mapped_column(Integer, default=0)


class DemandStat(Base):
    """행정동 × 시간대 수요. 예비 표 (지금은 적재하지 않음). 수요는 역 단위 subway_station_stat을 쓴다."""

    __tablename__ = "demand_stat"

    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), primary_key=True)
    hour: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    subway_riders: Mapped[float | None] = mapped_column(Float)
    living_population: Mapped[float | None] = mapped_column(Float)


class SubwayStationStat(Base):
    """역별 하루 평균 수요 집계 (demand/subway_demand_202409_202609.csv)."""

    __tablename__ = "subway_station_stat"

    station_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    adm_cd: Mapped[str] = mapped_column(ForeignKey("dong.adm_cd"), index=True)
    gu: Mapped[str] = mapped_column(String(20))
    weekday_daily_riders: Mapped[float] = mapped_column(Float)
    weekend_daily_riders: Mapped[float] = mapped_column(Float)
    weekly_daily_riders: Mapped[float] = mapped_column(Float, index=True)
    weekend_weekday_ratio: Mapped[float] = mapped_column(Float)
    morning_alighting: Mapped[float] = mapped_column(Float)
    morning_boarding: Mapped[float] = mapped_column(Float)
    office_density: Mapped[float] = mapped_column(Float)
    evening_alighting: Mapped[float] = mapped_column(Float)
    night_boarding: Mapped[float] = mapped_column(Float)
