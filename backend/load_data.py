import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select

from app import models as _models
from app.core.database import Base, SessionLocal, engine
from app.models import (
    Category,
    CompetitionStat,
    Dong,
    MetaSource,
    StabilityAggregateStat,
    StabilityStat,
    StoreDong,
    SubwayStationStat,
    UptaeCount,
)

REPO_DIR = Path(__file__).resolve().parent.parent
CATEGORY_CODES = {"카페": "cafe", "제과점": "bakery", "한식": "korean"}
BASIS_CODES = {"행정동": "dong", "구 평균": "gu", "없음": "none"}


def read_csv(relative_path: str) -> list[dict[str, str]]:
    path = REPO_DIR / relative_path
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def as_int(value: str) -> int:
    return int(value) if value.strip() else 0


def as_float(value: str) -> float | None:
    return float(value) if value.strip() else None


def make_stability_values(row: dict[str, str], category_code: str) -> dict[str, Any]:
    return {
        "category_code": category_code,
        "base_date": date.fromisoformat(row["기준일"]),
        "open_base": as_int(row["영업중_기초"]),
        "open_now": as_int(row["영업중_현재"]),
        "new_1y": as_int(row["신규_1년"]),
        "closed_1y": as_int(row["폐업_1년"]),
        "cohort_3y": as_int(row["3년_코호트"]),
        "survived_3y": as_int(row["3년_생존"]),
        "turnover_rate": as_float(row["교체율"]),
        "new_rate": as_float(row["신규율"]),
        "survival_rate": as_float(row["3년_생존율"]),
    }


def load_source_rows() -> dict[type, list[dict[str, Any]]]:
    dong_csv = read_csv("competition/dong_area.csv")
    competition_csv = read_csv("competition/competition_by_dong.csv")
    stability_csv = read_csv("stability/data/stability_by_dong.csv")
    stability_gu_csv = read_csv("stability/data/stability_by_gu.csv")
    stability_seoul_csv = read_csv("stability/data/stability_seoul.csv")
    demand_csv = read_csv("demand/subway_demand_202409_202609.csv")
    store_dong_csv = read_csv("jari/dong_fill.csv")
    uptae_csv = read_csv("competition/uptae_counts.csv")

    dong_rows = [
        {
            "adm_cd": row["adm_cd"],
            "adm_cd8": row["adm_cd8"],
            "stat_cd": row["stat_cd"],
            "name": row["adm_nm"],
            "gu": row["gu"],
            "area_km2": float(row["area_km2"]),
        }
        for row in dong_csv
    ]
    adm_codes = {row["adm_cd"] for row in dong_rows}
    if len(adm_codes) != len(dong_rows):
        raise ValueError("competition/dong_area.csv에 중복 adm_cd가 있습니다.")

    category_rows = [
        {"code": code, "name": name, "sort_order": order}
        for order, (name, code) in enumerate(CATEGORY_CODES.items(), start=1)
    ]

    competition_rows = []
    for row in competition_csv:
        for display_name, code in CATEGORY_CODES.items():
            competition_rows.append(
                {
                    "adm_cd": row["adm_cd"],
                    "category_code": code,
                    "open_count": as_int(row[display_name]),
                    "density_per_km2": float(row[f"{display_name}_밀도(개/km2)"]),
                }
            )

    stability_rows = []
    for row in stability_csv:
        category_code = CATEGORY_CODES[row["category"]]
        stability_rows.append(
            {
                "adm_cd": row["adm_cd"],
                "open_base": as_int(row["영업중_기초"]),
                "open_now": as_int(row["영업중_현재"]),
                "new_1y": as_int(row["신규_1년"]),
                "closed_1y": as_int(row["폐업_1년"]),
                "cohort_3y": as_int(row["3년_코호트"]),
                "survival_3y": as_float(row["3년_생존율"]),
                "turnover_rate": as_float(row["교체율"]),
                "new_rate": as_float(row["신규율"]),
                "display_turnover_rate": as_float(row["표시_교체율"]),
                "display_new_rate": as_float(row["표시_신규율"]),
                "display_survival_3y": as_float(row["표시_3년_생존율"]),
                "turnover_basis": BASIS_CODES[row["교체율_기준"]],
                "new_rate_basis": BASIS_CODES[row["신규율_기준"]],
                "survival_basis": BASIS_CODES[row["3년_생존율_기준"]],
                "flow_type": None,
                "category_code": category_code,
            }
        )

    stability_aggregate_rows = []
    for scope, rows, area_column in (
        ("gu", stability_gu_csv, "gu"),
        ("seoul", stability_seoul_csv, "범위"),
    ):
        for row in rows:
            values = make_stability_values(row, CATEGORY_CODES[row["category"]])
            stability_aggregate_rows.append(
                {
                    "scope": scope,
                    "area_name": row[area_column],
                    **values,
                }
            )

    demand_rows = [
        {
            "station_name": row["SUB_STA_NM"],
            "adm_cd": row["adm_cd"],
            "gu": row["gu"],
            "weekday_daily_riders": float(row["평일_일평균_승하차"]),
            "weekend_daily_riders": float(row["주말_일평균_승하차"]),
            "weekly_daily_riders": float(row["주간_일평균_승하차"]),
            "weekend_weekday_ratio": float(row["주말_평일_비율"]),
            "morning_alighting": float(row["아침_수요지수(출근하차)"]),
            "morning_boarding": float(row["아침_승차인원"]),
            "office_density": float(row["오피스_밀집도"]),
            "evening_alighting": float(row["저녁_집객지수(유입)"]),
            "night_boarding": float(row["심야_귀가지수(유흥/회식)"]),
        }
        for row in demand_csv
    ]

    store_dong_rows = []
    for row in store_dong_csv:
        if row["is_open"].strip().lower() not in {"true", "false", "1", "0"}:
            raise ValueError(f"알 수 없는 is_open 값: {row['is_open']!r}")
        store_dong_rows.append(
            {
                "source": row["source"],
                "mgt_no": row["mgt_no"],
                "adm_cd": row["adm_cd"],
                "adm_nm": row["adm_nm"],
                "gu": row["gu"],
                "via": row["via"],
                "is_open": row["is_open"].strip().lower() in {"true", "1"},
            }
        )

    uptae_rows = [
        {"source": row["source"], "uptae": row["uptae"] or None, "count": as_int(row["count"])}
        for row in uptae_csv
    ]

    source_rows = [
        {
            "key": "permits-base",
            "name": "공용 지방행정 인허가 데이터",
            "provider": "행정안전부 원천, 서울열린데이터광장 제공",
            "url": "https://data.seoul.go.kr/",
            "axis": "competition, stability, site",
            "fetched_at": None,
        },
        {
            "key": "subway-ridership",
            "name": "서울 지하철 역별 승하차",
            "provider": "서울열린데이터광장",
            "url": "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do",
            "axis": "demand",
            "fetched_at": None,
        },
        {
            "key": "dong-boundaries",
            "name": "행정동 기준표·경계",
            "provider": "경쟁 축 기준표, vuski/admdongkor",
            "url": "https://github.com/vuski/admdongkor",
            "axis": "all",
            "fetched_at": None,
        },
    ]

    datasets = {
        Dong: dong_rows,
        Category: category_rows,
        MetaSource: source_rows,
        CompetitionStat: competition_rows,
        StabilityStat: stability_rows,
        StabilityAggregateStat: stability_aggregate_rows,
        SubwayStationStat: demand_rows,
        StoreDong: store_dong_rows,
        UptaeCount: uptae_rows,
    }

    for model, rows in datasets.items():
        if model in {CompetitionStat, StabilityStat, SubwayStationStat, StoreDong}:
            invalid_codes = sorted({row["adm_cd"] for row in rows} - adm_codes)
            if invalid_codes:
                raise ValueError(f"{model.__tablename__}에 기준표에 없는 adm_cd가 있습니다: {invalid_codes[:5]}")
    for model, rows in datasets.items():
        print(f"{model.__tablename__}: {len(rows):,} rows")
    print("not loaded: site/site_store (jari/data/seoul/sites.csv, site_history.csv 없음)")
    print("not loaded: store (공용 permits_base.csv는 드라이브 공유, 로컬에 없음)")
    print("not loaded: yearly_stat (stability/out/yearly_by_dong.csv는 로컬에 없음)")
    print("not loaded: demand_stat (시간대별 행정동 자료 대신 역별 집계 CSV를 별도 테이블에 저장)")
    return datasets


def ensure_empty_database() -> None:
    existing_tables = set(inspect(engine).get_table_names())
    model_tables = set(Base.metadata.tables)
    populated = []
    if existing_tables & model_tables:
        with SessionLocal() as session:
            for table_name in sorted(existing_tables & model_tables):
                table = Base.metadata.tables[table_name]
                count = session.scalar(select(func.count()).select_from(table)) or 0
                if count:
                    populated.append(f"{table_name}={count}")
    if populated:
        raise RuntimeError(
            "대상 DB에 기존 애플리케이션 데이터가 있어 적재를 중단했습니다. "
            "기존 데이터를 지우지 않았습니다: " + ", ".join(populated)
        )


def load(datasets: dict[type, list[dict[str, Any]]]) -> None:
    ensure_empty_database()
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        for model, rows in datasets.items():
            for start in range(0, len(rows), 2_000):
                session.bulk_insert_mappings(model, rows[start : start + 2_000])


def main() -> None:
    parser = argparse.ArgumentParser(description="Load checked-in axis CSVs into the configured PostgreSQL database.")
    parser.add_argument("--dry-run", action="store_true", help="validate CSVs and row counts without connecting to the database")
    args = parser.parse_args()
    datasets = load_source_rows()
    if not args.dry_run:
        load(datasets)
        print("load complete")


if __name__ == "__main__":
    main()