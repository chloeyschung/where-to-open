"""데이터 분석 페이지(index.html)가 읽는 data.js 를 만든다.

숫자는 모두 이 스크립트가 결과 파일에서 계산한다. 페이지에 손으로 숫자를 적지 않는다.
입력
  저장소: competition/, stability/data/, demand/ 결과 파일
  data/ (드라이브에서 받기, git에 없음): data/base/permits_base.csv, data/seoul/sites.csv, data/seoul/site_history.csv
실행 (저장소 맨 위에서)
  python frontend-html/analysis/build_data.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("data.js")  # 파일로 바로 열어도 되게 window.ANALYSIS 로 내보냄
BASE = "2026-09-30"
CATS = ["카페", "제과점", "한식"]
MIN_WEEKDAY = 20000  # 오피스형·주말형 역을 고를 때 평일 하루 승하차 최소값


def csv(path, **kw):
    return pd.read_csv(ROOT / path, encoding="utf-8-sig", **kw)


def r(x, n=1):
    return None if pd.isna(x) else round(float(x), n)


# ---------------------------------------------------------------- 입력
dong = csv("competition/dong_area.csv", dtype={"adm_cd": str})
comp = csv("competition/competition_by_dong.csv", dtype={"adm_cd": str})
st_seoul = csv("stability/data/stability_seoul.csv")
st_dong = csv("stability/data/stability_by_dong.csv", dtype={"adm_cd": str})
demand = csv("demand/subway_demand_202409_202609.csv", dtype={"adm_cd": str})
permits = csv("data/base/permits_base.csv", dtype=str)
sites = csv("data/seoul/sites.csv", dtype={"adm_cd": str})
history = csv("data/seoul/site_history.csv", dtype=str)

o, c = pd.to_datetime(permits.permit_date), pd.to_datetime(permits.close_date)
open_base = (o <= BASE) & (c.isna() | (c > BASE)) & (permits.close_date_missing == "False") & (permits.is_temp == "False")
cat = permits.category.isin(CATS)

# ---------------------------------------------------------------- 한눈에
open_by_cat = st_seoul.set_index("category")["영업중_현재"].reindex(CATS)
overview = {
    "base_date": BASE,
    "dongs": int(len(dong)),
    "permits_total": int(len(permits)),
    "permits_in_categories": int(cat.sum()),
    "open_by_category": {k: int(v) for k, v in open_by_cat.items()},
    "open_total": int(open_by_cat.sum()),
    "popups_removed": int((permits.is_temp == "True").sum()),
    "popups_removed_in_categories": int(((permits.is_temp == "True") & cat).sum()),
    "close_date_missing": int((permits.close_date_missing == "True").sum()),
    "stations": int(len(demand)),
    "sites_10y": int(len(sites)),
}
# 공용 파일로 센 9/30 영업 중 = 안정성 서울 값 (두 축이 같은 가게를 세는지 확인)
check = permits[open_base & cat].groupby("category").size().reindex(CATS)
assert (check.values == open_by_cat.values).all(), (check, open_by_cat)

# ---------------------------------------------------------------- 경쟁: 업종별 밀도 상위 동네
competition = {
    k: [{"dong": f"{row['gu']} {row['adm_nm']}", "density": r(row[f"{k}_밀도(개/km2)"]), "count": int(row[k])}
        for _, row in comp.dropna(subset=[f"{k}_밀도(개/km2)"]).sort_values(f"{k}_밀도(개/km2)", ascending=False).head(10).iterrows()]
    for k in CATS
}

# ---------------------------------------------------------------- 안정성: 서울 업종별
stability = []
for _, row in st_seoul.set_index("category").reindex(CATS).iterrows():
    stability.append({
        "category": row.name,
        "open": int(row["영업중_현재"]),
        "turnover": r(row["교체율"] * 100),
        "new_rate": r(row["신규율"] * 100),
        "survival_3y": r(row["3년_생존율"] * 100),
        "closed_1y": int(row["폐업_1년"]),
        "new_1y": int(row["신규_1년"]),
    })
dong_value_share = {
    k: {"turnover_dong": int(((st_dong.category == k) & (st_dong["교체율_기준"] == "행정동")).sum()),
        "survival_dong": int(((st_dong.category == k) & (st_dong["3년_생존율_기준"] == "행정동")).sum()),
        "dongs": int((st_dong.category == k).sum())}
    for k in CATS
}

# ---------------------------------------------------------------- 자리
single = sites[sites.max_concurrent == 1]
dist = single.permits_10y.clip(upper=6).value_counts().sort_index()
demo_key = "중구 황학동 479"
assert (sites.site_key == demo_key).sum() == 1, demo_key  # 예시 자리가 정확히 한 줄인지
demo = sites.set_index("site_key").loc[demo_key]
demo_hist = history[history.site_key == demo_key].sort_values("opened")
jari = {
    "sites_10y": int(len(sites)),
    "single_sites": int(len(single)),
    "single_avg": r(single.permits_10y.mean(), 2),
    "single_4plus": int((single.permits_10y >= 4).sum()),
    "distribution": [{"permits": int(k), "label": f"{int(k)}건" + (" 이상" if k == 6 else ""), "sites": int(v)} for k, v in dist.items()],
    "demo": {
        "site": demo_key,
        "dong": demo["hemd_name"],
        "permits_10y": int(demo["permits_10y"]),
        "dong_avg_single": r(demo["dong_avg_single"], 2),
        "history": [{"name": h["name"], "uptae": h["uptae"], "opened": h["opened"], "closed": h["closed"] if isinstance(h["closed"], str) else "",
                     "months": int(h["months"])} for _, h in demo_hist.iterrows()],
    },
    "top_per_slot": [{"site": x.site_key, "dong": x.hemd_name, "per_slot": r(x.per_slot_10y, 1), "permits": int(x.permits_10y)}
                     for x in single.sort_values("per_slot_10y", ascending=False).head(5).itertuples()],
}

# ---------------------------------------------------------------- 수요
d = demand.copy()
d["name"] = d.SUB_STA_NM
d["where"] = d.gu + " " + d.adm_nm
office = d[d["평일_일평균_승하차"] >= MIN_WEEKDAY].sort_values("오피스_밀집도", ascending=False).head(5)
weekend = d[d["평일_일평균_승하차"] >= MIN_WEEKDAY].sort_values("주말_평일_비율", ascending=False).head(5)
demand_out = {
    "stations": int(len(d)),
    "dongs_with_station": int(d.adm_cd.nunique()),
    "top": [{"station": x["name"], "where": x["where"], "weekly": int(round(x["주간_일평균_승하차"])),
             "weekday": int(round(x["평일_일평균_승하차"])), "weekend": int(round(x["주말_일평균_승하차"]))}
            for _, x in d.sort_values("주간_일평균_승하차", ascending=False).head(10).iterrows()],
    "office": [{"station": x["name"], "where": x["where"], "ratio": r(x["오피스_밀집도"], 1)} for _, x in office.iterrows()],
    "weekend": [{"station": x["name"], "where": x["where"], "ratio": r(x["주말_평일_비율"], 2)} for _, x in weekend.iterrows()],
    "min_weekday_for_types": MIN_WEEKDAY,
}

# ---------------------------------------------------------------- 출처 (각 페이지에서 이름 확인, 2026-10-17)
sources = [
    {"name": "서울시 일반음식점 인허가 정보", "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "url": "https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do", "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072404(자리·안정성 축 수집)", "axes": "경쟁·안정성·자리"},
    {"name": "서울시 휴게음식점 인허가 정보", "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "url": "https://data.seoul.go.kr/dataList/OA-16095/S/1/datasetView.do", "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072405", "axes": "경쟁·안정성·자리"},
    {"name": "서울시 제과점영업 인허가 정보", "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
     "url": "https://data.seoul.go.kr/dataList/OA-16084/S/1/datasetView.do", "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072218", "axes": "경쟁·안정성·자리"},
    {"name": "서울시 지하철호선별 역별 승하차 인원 정보 (일별)", "org": "서울특별시",
     "url": "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do", "method": "월별 CSV 내려받기 (2024-09~2026-09)", "axes": "수요"},
    {"name": "서울시 지하철 호선별 역별 시간대별 승하차 인원 정보", "org": "서울특별시",
     "url": "https://data.seoul.go.kr/dataList/OA-12252/S/1/datasetView.do", "method": "Open API CardSubwayTime (2024-09~2026-09)", "axes": "수요"},
    {"name": "서울시 역사마스터 정보 (역 좌표)", "org": "서울특별시",
     "url": "https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do", "method": "파일", "axes": "수요 (역 → 행정동)"},
    {"name": "도로명주소 검색 API", "org": "행정안전부",
     "url": "https://business.juso.go.kr", "method": "Open API (지번·도로명주소 → 행정동)", "axes": "자리 (좌표 없는 가게 행정동 채우기)"},
    {"name": "행정동 경계 (admdongkor ver20260701)", "org": "vuski/admdongkor (GitHub)",
     "url": "https://github.com/vuski/admdongkor", "method": "파일 (2026-07-01 행정구역)", "axes": "전체 (좌표 → 행정동, 면적)"},
    {"name": "소상공인시장진흥공단 상가(상권)정보 (2026-06)", "org": "소상공인시장진흥공단",
     "url": "https://www.data.go.kr/data/15083033/fileData.do", "method": "파일 (검증용: 신고 없이 닫은 가게 규모 확인)", "axes": "자리 (검증)"},
]

data = {"overview": overview, "sources": sources, "competition": competition, "stability": stability,
        "stability_dong_share": dong_value_share, "jari": jari, "demand": demand_out}
OUT.write_text("// build_data.py 가 만든 파일. 직접 고치지 말 것\nwindow.ANALYSIS = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
print("저장:", OUT.relative_to(ROOT))
print(json.dumps(overview, ensure_ascii=False))
