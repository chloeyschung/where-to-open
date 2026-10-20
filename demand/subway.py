import argparse
import json
import os
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent.parent
API_BASE_URL = "http://openapi.seoul.go.kr:8088"
API_KEY_ENV = "SEOUL_API_KEY"  # 저장소 맨 위 .env (다른 축과 같은 키)

# 같은 역인데 기간(이름 변경)이나 노선(환승역)에 따라 이름이 다른 경우 → 이름 하나로 합친다
# 역사마스터 좌표로 같은 위치인 것을 확인함. 새절(신사)와 신사, 용산과 신용산처럼 가까워도 다른 역은 합치지 않는다
STATION_ALIASES = {
    "당고개": "불암산",                              # 4호선, 2025-04 이름 변경
    "삼각지": "삼각지(전쟁기념관)",                   # 4·6호선, 2025-04 이름 변경
    "숙대입구(갈월)": "숙대입구(서울시교육청)",       # 4호선, 2026-07 이름 변경
    "이수": "총신대입구(이수)",                      # 7호선 이름. 4호선은 총신대입구(이수)인 같은 환승역
}
# 이름은 같지만 노선에 따라 다른 역 → 노선을 붙여 나눈다 (역사마스터 좌표가 714m, 53km 떨어짐)
LINE_SPECIFIC_NAMES = {
    ("신촌", "경의선"): "신촌(경의중앙선)",   # 2호선 신촌과 다른 역
    ("양평", "중앙선"): "양평(중앙선)",       # 경기 양평군. 5호선 양평(영등포구)과 다른 역
}


def _unify_station_names(df):
    """노선별로 다른 같은 이름을 먼저 나누고, 같은 역의 다른 이름을 하나로 합친다."""
    for (name, line), new_name in LINE_SPECIFIC_NAMES.items():
        df.loc[(df["SUB_STA_NM"] == name) & (df["LINE_NUM"] == line), "SUB_STA_NM"] = new_name
    df["SUB_STA_NM"] = df["SUB_STA_NM"].replace(STATION_ALIASES)
    return df


def _load_root_env():
    """저장소 맨 위 .env 를 환경변수로 읽는다 (이미 설정된 값은 그대로)."""
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip())


_load_root_env()
DAILY_ARCHIVE_PAGE = "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do"
DAILY_ARCHIVE_DOWNLOAD = (
    "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
)
# 기간: 월 배치(batch/run.py)는 환경변수로 최근 25개월을 넘겨준다. 없으면 2024-09-01 ~ 2026-09-30
START_DATE = os.environ.get("WTO_DEMAND_START", "20240901")
END_DATE = os.environ.get("WTO_DEMAND_END", "20260930")
PAGE_SIZE = 1000


def _fetch_rows(service, query_value, api_key, session):
    """서울 열린데이터광장 API에서 해당 일자/월의 전체 행을 가져온다."""
    rows = []
    start_index = 1

    while True:
        end_index = start_index + PAGE_SIZE - 1
        url = (
            f"{API_BASE_URL}/{api_key}/json/{service}/"
            f"{start_index}/{end_index}/{query_value}"
        )
        response = session.get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        service_data = payload.get(service)

        if service_data is None:
            result = payload.get("RESULT", {})
            if result.get("CODE") == "INFO-200":
                return rows
            raise RuntimeError(
                f"{service} API 오류 ({result.get('CODE')}): "
                f"{result.get('MESSAGE', '응답 데이터가 없습니다.')}"
            )

        result = service_data.get("RESULT", {})
        if result and result.get("CODE") not in (None, "INFO-000"):
            raise RuntimeError(
                f"{service} API 오류 ({result.get('CODE')}): "
                f"{result.get('MESSAGE', '요청에 실패했습니다.')}"
            )

        page_rows = service_data.get("row", [])
        rows.extend(page_rows)
        total_count = int(service_data.get("list_total_count", len(rows)))
        if not page_rows or len(rows) >= total_count:
            break
        start_index = end_index + 1

    return rows


def _get_api_key():
    api_key = os.getenv(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"서울 열린데이터광장 인증키를 환경변수 {API_KEY_ENV}에 설정하세요."
        )
    return api_key


def get_daily_subway_data(start_date, end_date, cache_dir=None):
    """월별 CSV 아카이브에서 과거 일별 역별 승하차 데이터를 수집한다.
    cache_dir 를 주면 받은 월 파일을 저장해 두고 다음 실행에 다시 쓴다."""
    start = pd.to_datetime(start_date, format="%Y%m%d")
    end = pd.to_datetime(end_date, format="%Y%m%d")
    months = pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")
    columns = [
        "USE_DT",
        "LINE_NUM",
        "SUB_STA_NM",
        "RIDE_PASGR_NUM",
        "ALIGHT_PASGR_NUM",
    ]
    monthly_frames = []

    with requests.Session() as session:
        page = session.get(DAILY_ARCHIVE_PAGE, timeout=30)
        page.raise_for_status()
        archive_ids = {
            month: file_id
            for month, file_id in re.findall(
                r'title=["\']CARD_SUBWAY_MONTH_(\d{6})\.csv["\'][^>]*?'
                r'downloadFile\(["\'](\d+)["\']\)',
                page.text,
            )
        }

        missing_months = [
            month.strftime("%Y%m")
            for month in months
            if month.strftime("%Y%m") not in archive_ids
        ]
        if missing_months:
            raise RuntimeError(
                "서울시 일별 CSV 아카이브에서 다음 월 파일을 찾지 못했습니다: "
                + ", ".join(missing_months)
            )

        for month in months:
            month_key = month.strftime("%Y%m")
            cached = Path(cache_dir) / f"daily_{month_key}.csv" if cache_dir else None
            if cached and cached.exists():
                content = cached.read_bytes()
            else:
                response = session.post(
                    DAILY_ARCHIVE_DOWNLOAD,
                    data={"infId": "OA-12914", "infSeq": "3", "seq": archive_ids[month_key]},
                    headers={"Referer": DAILY_ARCHIVE_PAGE},
                    timeout=60,
                )
                response.raise_for_status()
                if response.content.startswith(b"<html"):
                    raise RuntimeError(f"{month_key} 일별 CSV 다운로드에 실패했습니다.")
                content = response.content
                if cached:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(content)

            csv_options = {"dtype": str, "usecols": range(6)}
            try:
                monthly_df = pd.read_csv(
                    BytesIO(content), encoding="utf-8-sig", **csv_options
                )
            except UnicodeDecodeError:
                monthly_df = pd.read_csv(
                    BytesIO(content), encoding="cp949", **csv_options
                )

            monthly_df = monthly_df.rename(
                columns={
                    "사용일자": "USE_DT",
                    "노선명": "LINE_NUM",
                    "역명": "SUB_STA_NM",
                    "승차총승객수": "RIDE_PASGR_NUM",
                    "하차총승객수": "ALIGHT_PASGR_NUM",
                }
            )
            monthly_frames.append(monthly_df[columns])

    df = pd.concat(monthly_frames, ignore_index=True)
    duplicated = int(df.duplicated(["USE_DT", "LINE_NUM", "SUB_STA_NM"]).sum())
    if duplicated:
        print(f"  일별: 같은 날·노선·역 중복 {duplicated}행 제거")
        df = df.drop_duplicates(["USE_DT", "LINE_NUM", "SUB_STA_NM"], keep="last")
    df["USE_DT"] = pd.to_datetime(df["USE_DT"], format="%Y%m%d")
    df = _unify_station_names(df)
    return df[df["USE_DT"].between(start, end)].copy()


def get_time_subway_data(start_month, end_month, cache_dir=None):
    """월별 역별 시간대 승하차 데이터(OA-12252)를 지정 기간 동안 수집한다.
    API가 같은 달 행을 두 번씩 돌려주는 경우가 있어(2026-03, 2026-07 확인) 완전히 같은 행은 하나만 남긴다."""
    api_key = _get_api_key()
    months = pd.period_range(
        pd.Period(start_month, freq="M"), pd.Period(end_month, freq="M"), freq="M"
    )
    rows = []

    with requests.Session() as session:
        for month in months:
            month_key = month.strftime("%Y%m")
            cached = Path(cache_dir) / f"time_{month_key}.json" if cache_dir else None
            if cached and cached.exists():
                month_rows = json.loads(cached.read_text(encoding="utf-8"))
            else:
                month_rows = _fetch_rows("CardSubwayTime", month_key, api_key, session)
                if cached:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(json.dumps(month_rows, ensure_ascii=False), encoding="utf-8")
            month_df = pd.DataFrame(month_rows)
            if len(month_df):
                # 같은 달·노선·역이 두 번 오면 하나만 남긴다 (등록일만 다른 행도 포함)
                keys = ["USE_MM", "SBWY_ROUT_LN_NM", "STTN"]
                duplicated = int(month_df.duplicated(keys).sum())
                if duplicated:
                    print(f"  시간대 {month_key}: 같은 달·노선·역 중복 {duplicated}행 제거")
                month_df = month_df.drop_duplicates(keys, keep="last")
            rows.extend(month_df.to_dict("records"))

    identity_columns = ["USE_MM", "LINE_NUM", "SUB_STA_NM"]
    hourly_columns = {
        f"HR_{hour}_GET_ON_NOPE": f"{hour:02d}-{hour + 1:02d}_승차"
        for hour in range(24)
    }
    hourly_columns.update(
        {
            f"HR_{hour}_GET_OFF_NOPE": f"{hour:02d}-{hour + 1:02d}_하차"
            for hour in range(24)
        }
    )
    columns = identity_columns + list(hourly_columns.values())
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows).rename(
        columns={
            "SBWY_ROUT_LN_NM": "LINE_NUM",
            "STTN": "SUB_STA_NM",
            **hourly_columns,
        }
    )
    df = _unify_station_names(df)
    return df[columns]


def build_station_demand(start_date=START_DATE, end_date=END_DATE, cache_dir=None):
    start_month = pd.to_datetime(start_date, format="%Y%m%d").strftime("%Y-%m")
    end_month = pd.to_datetime(end_date, format="%Y%m%d").strftime("%Y-%m")
    df_daily = get_daily_subway_data(start_date, end_date, cache_dir)
    df_time = get_time_subway_data(start_month, end_month, cache_dir)

    if df_daily.empty or df_time.empty:
        raise RuntimeError("지정한 기간의 지하철 데이터를 가져오지 못했습니다.")

    df_daily["USE_DT"] = pd.to_datetime(df_daily["USE_DT"], format="%Y%m%d")
    df_daily["RIDE_PASGR_NUM"] = pd.to_numeric(df_daily["RIDE_PASGR_NUM"])
    df_daily["ALIGHT_PASGR_NUM"] = pd.to_numeric(df_daily["ALIGHT_PASGR_NUM"])
    df_daily["IS_WEEKEND"] = (df_daily["USE_DT"].dt.dayofweek >= 5).astype(int)
    df_daily["TOTAL_PASGR"] = (
        df_daily["RIDE_PASGR_NUM"] + df_daily["ALIGHT_PASGR_NUM"]
    )
    df_daily = df_daily.groupby(
        ["USE_DT", "SUB_STA_NM", "IS_WEEKEND"], as_index=False
    )["TOTAL_PASGR"].sum()

    daily_grouped = (
        df_daily.groupby(["SUB_STA_NM", "IS_WEEKEND"])["TOTAL_PASGR"]
        .mean()
        .unstack()
        .reindex(columns=[0, 1])
    )
    # 승차 + 하차 인원의 하루 평균 (한 사람이 타고 내리면 두 번 셈. 유동인구가 아님)
    daily_grouped.columns = ["평일_일평균_승하차", "주말_일평균_승하차"]
    daily_grouped["주간_일평균_승하차"] = (
        daily_grouped["평일_일평균_승하차"] * 5 + daily_grouped["주말_일평균_승하차"] * 2
    ) / 7
    weekday_average = daily_grouped["평일_일평균_승하차"]
    daily_grouped["주말_평일_비율"] = daily_grouped["주말_일평균_승하차"].div(
        weekday_average.where(weekday_average != 0)
    )
    daily_grouped = daily_grouped.reset_index()

    hourly_value_columns = [
        column for column in df_time.columns if column not in {"USE_MM", "LINE_NUM", "SUB_STA_NM"}
    ]
    for column in hourly_value_columns:
        df_time[column] = pd.to_numeric(df_time[column], errors="coerce")
    df_time["DAYS_IN_MONTH"] = pd.to_datetime(
        df_time["USE_MM"], format="%Y%m"
    ).dt.days_in_month
    df_time[hourly_value_columns] = df_time[hourly_value_columns].div(
        df_time["DAYS_IN_MONTH"], axis=0
    )
    monthly_station_time = df_time.groupby(
        ["USE_MM", "SUB_STA_NM"], as_index=False
    )[hourly_value_columns].sum()
    df_time_features = monthly_station_time.groupby("SUB_STA_NM", as_index=False)[
        hourly_value_columns
    ].mean()
    df_time_features["아침_수요지수(출근하차)"] = (
        df_time_features["07-08_하차"] + df_time_features["08-09_하차"]
    )
    df_time_features["아침_승차인원"] = (
        df_time_features["07-08_승차"] + df_time_features["08-09_승차"]
    )
    morning_boardings = df_time_features["아침_승차인원"]
    df_time_features["오피스_밀집도"] = df_time_features[
        "아침_수요지수(출근하차)"
    ].div(morning_boardings.where(morning_boardings != 0))
    df_time_features["저녁_집객지수(유입)"] = (
        df_time_features["18-19_하차"] + df_time_features["19-20_하차"]
    )
    df_time_features["심야_귀가지수(유흥/회식)"] = df_time_features["22-23_승차"]

    only_daily = sorted(set(daily_grouped["SUB_STA_NM"]) - set(df_time_features["SUB_STA_NM"]))
    only_time = sorted(set(df_time_features["SUB_STA_NM"]) - set(daily_grouped["SUB_STA_NM"]))
    if only_daily or only_time:
        print(f"  일별에만 있는 역 {len(only_daily)}개 {only_daily}, 시간대에만 있는 역 {len(only_time)}개 {only_time} → 결과에서 빠짐")

    final_demand_df = pd.merge(
        daily_grouped,
        df_time_features[
            [
                "SUB_STA_NM",
                "아침_수요지수(출근하차)",
                "아침_승차인원",
                "오피스_밀집도",
                "저녁_집객지수(유입)",
                "심야_귀가지수(유흥/회식)",
            ]
        ],
        on="SUB_STA_NM",
        how="inner",
    )
    return final_demand_df.sort_values(
        by="주간_일평균_승하차", ascending=False
    ).reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="역별 지하철 수요 지표 (2024-09 ~ 2026-09)")
    parser.add_argument("--cache", help="받은 원본(월별 일별 CSV·시간대 JSON)을 저장하고 다시 쓸 폴더")
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("subway_demand_202409_202609.csv"),
                        help="결과 파일 (기본: 이 폴더의 subway_demand_202409_202609.csv)")
    args = parser.parse_args()
    final_demand_df = build_station_demand(cache_dir=args.cache)
    output_path = args.out
    final_demand_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(final_demand_df.head(20).to_string(index=False))
    print(f"\n전체 결과 저장: {output_path}")