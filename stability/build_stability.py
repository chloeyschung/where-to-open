"""
안정성 축 집계: 서울 전체 행정동 × 업종 대분류

입력
  raw/LOCALDATA_072404.csv, raw/LOCALDATA_072405.csv   (collect.py 결과)
  행정동 경계 GeoJSON                                    (없으면 자동 다운로드)
  category_map.csv                                        (업태 → 대분류 규칙, 수정 가능)

출력 (out/)
  stability_by_dong.csv     행정동 × 업종 지표 (메인 산출물)
  stability_by_gu.csv       자치구 × 업종 지표 (비교 기준)
  stability_seoul.csv       서울 전체 × 업종 지표 (비교 기준)
  yearly_by_dong.csv        행정동 × 업종 × 연도 신규·폐업 건수 (데이터 분석 페이지용)
  stores_clean.csv          업소 단위 정제본 (행정동 코드 부착; 경쟁·자리 축에서 재사용)
  category_mapping_used.csv 원본 업태명 → 대분류 매핑 결과 (검토용)
  quality_report.json       결측·매핑 실패·좌표계 검증 결과

지표 정의 (기준일 B, 기본값: 실행일)
  영업중_기초   = B-1년 시점에 영업 중이던 업소 수
  영업중_현재   = B 시점에 영업 중인 업소 수
  신규_1년      = (B-1년, B] 에 인허가된 업소 수
  폐업_1년      = (B-1년, B] 에 폐업한 업소 수
  교체율        = 폐업_1년 / 영업중_기초
  신규율        = 신규_1년 / 영업중_기초     (교체율과 항상 나란히 본다)
  3년_코호트    = [B-8년, B-3년] 에 인허가된 업소 수
  3년_생존      = 그중 영업 중이거나, 폐업했어도 영업기간이 3년 이상인 업소 수
  3년_생존율    = 3년_생존 / 3년_코호트
  (분모가 --min-n 미만이면 비율을 비우고 표본부족 표시)

영업상태 처리
  폐업         → 폐업일자(DCBYMD) 기준으로 폐업 처리. 폐업일 없는 건은 시점 지표에서 제외
  휴업         → 영업 중으로 간주
  취소/말소/만료/정지/중지 등 → 행정처분이라 창업·폐업 흐름과 성격이 달라 전부 제외

사용법
  python build_stability.py
  python build_stability.py --base-date 2026-09-30 --min-n 20
"""
import argparse
import json
import os
import urllib.request
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

BOUNDARY_URL = ("https://raw.githubusercontent.com/vuski/admdongkor/master/"
                "ver20260701/HangJeongDong_ver20260701.geojson")
SOURCES = {"LOCALDATA_072404": "일반음식점", "LOCALDATA_072405": "휴게음식점"}
CRS_CANDIDATES = ["EPSG:5174", "EPSG:5181"]  # 문서상 5174, 신규 데이터셋 설명은 GRS80(5181) → 실측으로 결정
ALL = "전체(음식·카페)"


# ---------------------------------------------------------------- 로드 · 정제
# 열린데이터광장/공공데이터포털에서 '내려받은' CSV는 컬럼명이 한글이라 API 이름으로 맞춘다
DOWNLOAD_COLUMNS = {
    "개방자치단체코드": "OPNSFTEAMCODE", "관리번호": "MGTNO", "인허가일자": "APVPERMYMD",
    "영업상태명": "TRDSTATENM", "상세영업상태명": "DTLSTATENM", "폐업일자": "DCBYMD",
    "소재지면적": "SITEAREA", "소재지전체주소": "SITEWHLADDR", "지번주소": "SITEWHLADDR",
    "도로명전체주소": "RDNWHLADDR", "도로명주소": "RDNWHLADDR", "사업장명": "BPLCNM",
    "최종수정시점": "LASTMODTS", "최종수정일자": "LASTMODTS", "데이터갱신일자": "UPDATEDT",
    "업태구분명": "UPTAENM",
    "좌표정보(x)": "X", "좌표정보(y)": "Y", "좌표정보(X)": "X", "좌표정보(Y)": "Y",
    "좌표정보x(epsg5174)": "X", "좌표정보y(epsg5174)": "Y",
}


def read_csv_any(path):
    """API 수집본은 utf-8, 내려받은 공공데이터 CSV는 대개 cp949"""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, encoding="cp949", encoding_errors="replace", low_memory=False)


def read_one(path, name):
    df = read_csv_any(path)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=DOWNLOAD_COLUMNS)
    df = df.loc[:, ~df.columns.duplicated()]
    missing = {"MGTNO", "APVPERMYMD", "TRDSTATENM", "DCBYMD", "UPTAENM", "X", "Y"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: 필요한 컬럼 없음 {missing}\n실제 컬럼: {list(df.columns)}")
    for c in ["SITEWHLADDR", "RDNWHLADDR", "UPDATEDT", "BPLCNM", "SITEAREA"]:
        if c not in df.columns:
            df[c] = ""
    if df["UPDATEDT"].fillna("").eq("").all() and "LASTMODTS" in df.columns:
        df["UPDATEDT"] = df["LASTMODTS"]
    df = df.fillna("")
    df["원천"] = name
    return df


def load_raw(raw_dir, overrides=None):
    """overrides: {서비스ID: 파일경로} — 내려받은 CSV로 대신 돌릴 때"""
    overrides = overrides or {}
    frames = []
    for svc, name in SOURCES.items():
        p = overrides.get(svc) or os.path.join(raw_dir, f"{svc}.csv")
        if not os.path.exists(p):
            raise FileNotFoundError(f"{p} 가 없습니다. 먼저 collect.py 를 실행하세요.")
        frames.append(read_one(p, name))
    df = pd.concat(frames, ignore_index=True)
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    # 서울 밖 주소가 섞인 파일(전국 다운로드 등)을 대비해 서울만 남긴다
    addr = df["SITEWHLADDR"].where(df["SITEWHLADDR"] != "", df["RDNWHLADDR"])
    df = df[addr.str.startswith("서울") | (addr == "")]
    return df


def to_date(s):
    """'2020-01-01', '2020-01-01 00:00', '20200101', '2020.01.01' 모두 처리"""
    digits = s.fillna("").str.replace(r"[^0-9]", "", regex=True).str.slice(0, 8)
    return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")


def load_category_map(path):
    m = pd.read_csv(path, dtype=str)
    return list(zip(m["keyword"], m["category"]))


def categorize(uptae, rules):
    for kw, cat in rules:
        if kw in uptae:
            return cat
    return "기타"


def clean(df, rules, q):
    q["원본_건수"] = int(len(df))
    # 같은 관리번호가 중복되면 최신 갱신분만 남긴다
    df = df.sort_values("UPDATEDT").drop_duplicates(["원천", "MGTNO"], keep="last")
    q["중복제거_후"] = int(len(df))

    df["인허가일"] = to_date(df["APVPERMYMD"])
    df["폐업일"] = to_date(df["DCBYMD"])
    st = df["TRDSTATENM"]
    df["상태구분"] = np.select(
        [st.str.contains("영업|정상"), st.str.contains("휴업"), st.str.contains("폐업")],
        ["영업", "휴업", "폐업"], default="행정처분등")
    q["영업상태_분포"] = df["TRDSTATENM"].value_counts().to_dict()

    drop_admin = df["상태구분"] == "행정처분등"
    q["제외_행정처분등"] = int(drop_admin.sum())
    df = df[~drop_admin]

    no_open = df["인허가일"].isna()
    q["제외_인허가일없음"] = int(no_open.sum())
    df = df[~no_open]

    # 영업/휴업 인데 폐업일이 찍혀 있으면 폐업일을 무시 (재개업 등 데이터 오류)
    df.loc[df["상태구분"] != "폐업", "폐업일"] = pd.NaT
    df["폐업일_결측"] = (df["상태구분"] == "폐업") & df["폐업일"].isna()
    q["폐업인데_폐업일없음(시점지표 제외)"] = int(df["폐업일_결측"].sum())

    bad_order = df["폐업일"].notna() & (df["폐업일"] < df["인허가일"])
    q["폐업일<인허가일(제외)"] = int(bad_order.sum())
    df = df[~bad_order]

    df["업종대분류"] = df["UPTAENM"].fillna("").map(lambda u: categorize(u, rules))
    excl = df["업종대분류"] == "제외"
    q["제외_업종(편의점·이동조리 등)"] = int(excl.sum())
    df = df[~excl]
    return df.copy()


# ---------------------------------------------------------------- 행정동 매핑
def load_boundary(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        print(f"행정동 경계 다운로드: {BOUNDARY_URL}")
        urllib.request.urlretrieve(BOUNDARY_URL, path)
    g = gpd.read_file(path)
    g = g[g["sidonm"] == "서울특별시"].copy()
    g["행정동코드"] = g["adm_cd2"].str.slice(0, 8)   # 서울 생활인구·상권분석 데이터와 같은 8자리
    g["행정동명"] = g["adm_nm"].str.split().str[-1]
    g["자치구"] = g["sggnm"]
    return g[["행정동코드", "adm_cd2", "adm_cd", "행정동명", "자치구", "geometry"]]


def gu_from_address(df):
    addr = df["SITEWHLADDR"].where(df["SITEWHLADDR"] != "", df["RDNWHLADDR"])
    return addr.str.split().str[1]


def spatial_join(df, g, crs):
    x = pd.to_numeric(df["X"], errors="coerce")
    y = pd.to_numeric(df["Y"], errors="coerce")
    ok = x.notna() & y.notna() & (x > 0) & (y > 0)
    pts = gpd.GeoDataFrame(df.loc[ok, []], geometry=gpd.points_from_xy(x[ok], y[ok]), crs=crs).to_crs(4326)
    j = gpd.sjoin(pts, g, how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    return j.drop(columns=["geometry", "index_right"], errors="ignore"), ok


def map_dong(df, g, q):
    addr_gu = gu_from_address(df)
    # 좌표계 후보별로 '주소상 자치구 = 경계상 자치구' 일치율을 재서 더 높은 쪽을 쓴다
    best = None
    q["좌표계_검증"] = {}
    for crs in CRS_CANDIDATES:
        j, ok = spatial_join(df, g, crs)
        both = j["자치구"].notna() & addr_gu.loc[j.index].notna()
        rate = float((j.loc[both, "자치구"] == addr_gu.loc[j.index][both]).mean()) if both.any() else 0.0
        q["좌표계_검증"][crs] = round(rate, 4)
        if best is None or rate > best[0]:
            best = (rate, crs, j, ok)
    rate, crs, j, ok = best
    q["채택_좌표계"] = crs
    q["좌표없음"] = int((~ok).sum())
    for c in ["행정동코드", "adm_cd2", "행정동명", "자치구"]:
        df[c] = j[c].reindex(df.index)
    q["서울경계밖_또는_매핑실패"] = int(ok.sum() - df["행정동코드"].notna().sum())
    df["좌표_자치구불일치"] = df["자치구"].notna() & (df["자치구"] != addr_gu)
    q["좌표·주소_자치구불일치(유지)"] = int(df["좌표_자치구불일치"].sum())
    mapped = df["행정동코드"].notna()
    q["행정동_매핑률"] = round(float(mapped.mean()), 4)
    return df


# ---------------------------------------------------------------- 지표 계산
def metrics(df, keys, B, min_n):
    B = pd.Timestamp(B)
    B1 = B - pd.DateOffset(years=1)
    c_lo, c_hi = B - pd.DateOffset(years=8), B - pd.DateOffset(years=3)
    o, c = df["인허가일"], df["폐업일"]
    timed = ~df["폐업일_결측"]

    def alive(t):
        return timed & (o <= t) & (c.isna() | (c > t))

    cohort = timed & (o >= c_lo) & (o <= c_hi)
    survived = cohort & (c.isna() | (c >= o + pd.DateOffset(years=3)))

    flags = pd.DataFrame({
        "영업중_기초": alive(B1),
        "영업중_현재": alive(B),
        "신규_1년": (o > B1) & (o <= B),
        "폐업_1년": c.notna() & (c > B1) & (c <= B),
        "3년_코호트": cohort,
        "3년_생존": survived,
    }).astype(int)
    agg = pd.concat([df[keys], flags], axis=1).groupby(keys, dropna=False).sum().reset_index()

    def ratio(num, den):
        r = agg[num] / agg[den].replace(0, np.nan)
        return r.where(agg[den] >= min_n).round(4)

    agg["교체율"] = ratio("폐업_1년", "영업중_기초")
    agg["신규율"] = ratio("신규_1년", "영업중_기초")
    agg["3년_생존율"] = ratio("3년_생존", "3년_코호트")
    agg["표본부족"] = (agg["영업중_기초"] < min_n) | (agg["3년_코호트"] < min_n)
    return agg


def add_all_category(df):
    d = df.copy()
    d["업종대분류"] = ALL
    return pd.concat([df, d], ignore_index=True)


def label_pattern(t, ref):
    """서울 전체 같은 업종 대비 신규율·교체율이 높은지/낮은지로 4분면 라벨 (판정이 아니라 설명용)"""
    r = t.merge(ref[["업종대분류", "교체율", "신규율"]].rename(columns={"교체율": "서울_교체율", "신규율": "서울_신규율"}),
                on="업종대분류", how="left")
    hi_c = r["교체율"] > r["서울_교체율"]
    hi_n = r["신규율"] > r["서울_신규율"]
    lab = np.select([hi_c & hi_n, hi_c & ~hi_n, ~hi_c & hi_n, ~hi_c & ~hi_n],
                    ["활발(많이 열고 많이 닫음)", "빠지는 상권(닫는 쪽 우세)", "유입 우세(새로 많이 열림)", "정체·안정(움직임 적음)"],
                    default="")
    r["흐름유형"] = np.where(r["교체율"].isna() | r["신규율"].isna(), "표본부족", lab)
    return r


def yearly(df, years=10, B=None):
    B = pd.Timestamp(B)
    y0 = B.year - years + 1
    d = df[df["행정동코드"].notna()]
    o = d.assign(연도=d["인허가일"].dt.year)
    o = o[o["연도"] >= y0].groupby(["행정동코드", "행정동명", "자치구", "업종대분류", "연도"]).size().rename("신규")
    c = d[d["폐업일"].notna()].assign(연도=lambda x: x["폐업일"].dt.year)
    c = c[c["연도"] >= y0].groupby(["행정동코드", "행정동명", "자치구", "업종대분류", "연도"]).size().rename("폐업")
    out = pd.concat([o, c], axis=1).fillna(0).astype(int).reset_index()
    out["순증"] = out["신규"] - out["폐업"]
    return out.sort_values(["행정동코드", "업종대분류", "연도"])


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--out", default="out")
    ap.add_argument("--boundary", default="ref/HangJeongDong_ver20260701.geojson")
    ap.add_argument("--category-map", default=os.path.join(os.path.dirname(__file__), "category_map.csv"))
    ap.add_argument("--base-date", default=date.today().isoformat())
    ap.add_argument("--min-n", type=int, default=20, help="비율을 낼 최소 분모")
    ap.add_argument("--restaurant-file", help="내려받은 일반음식점 CSV로 대신 실행 (교차검증용)")
    ap.add_argument("--cafe-file", help="내려받은 휴게음식점 CSV로 대신 실행 (교차검증용)")
    a = ap.parse_args()
    overrides = {k: v for k, v in {"LOCALDATA_072404": a.restaurant_file,
                                    "LOCALDATA_072405": a.cafe_file}.items() if v}
    os.makedirs(a.out, exist_ok=True)
    q = {"기준일": a.base_date, "최소표본": a.min_n}

    rules = load_category_map(a.category_map)
    q["입력"] = {k: overrides.get(k, os.path.join(a.raw, f"{k}.csv")) for k in SOURCES}
    df = clean(load_raw(a.raw, overrides), rules, q)
    g = load_boundary(a.boundary)
    df = map_dong(df, g, q)

    # 업태 매핑 검토표
    (df.groupby(["원천", "UPTAENM", "업종대분류"]).size().rename("건수").reset_index()
       .sort_values("건수", ascending=False)
       .to_csv(os.path.join(a.out, "category_mapping_used.csv"), index=False, encoding="utf-8-sig"))

    d_all = add_all_category(df)
    seoul = metrics(d_all, ["업종대분류"], a.base_date, a.min_n)
    seoul.insert(0, "범위", "서울")
    gu = metrics(d_all[d_all["자치구"].notna()], ["자치구", "업종대분류"], a.base_date, a.min_n)
    dong = metrics(d_all[d_all["행정동코드"].notna()], ["행정동코드", "행정동명", "자치구", "업종대분류"],
                   a.base_date, a.min_n)

    # 업소가 하나도 없는 행정동×업종도 행으로 남겨 조인이 깨지지 않게 한다
    cats = sorted(d_all["업종대분류"].unique())
    # adm_cd(행안부 10자리)도 붙여 competition/competition_by_dong.csv 와 바로 조인되게 한다
    grid = (g[["adm_cd2", "행정동코드", "행정동명", "자치구"]].drop_duplicates()
            .rename(columns={"adm_cd2": "adm_cd"})
            .merge(pd.DataFrame({"업종대분류": cats}), how="cross"))
    dong = grid.merge(dong, on=["행정동코드", "행정동명", "자치구", "업종대분류"], how="left")
    for col in ["영업중_기초", "영업중_현재", "신규_1년", "폐업_1년", "3년_코호트", "3년_생존"]:
        dong[col] = dong[col].fillna(0).astype(int)
    dong["표본부족"] = (dong["영업중_기초"] < a.min_n) | (dong["3년_코호트"] < a.min_n)

    dong = label_pattern(dong, seoul)
    gu = label_pattern(gu, seoul)
    dong.insert(0, "기준일", a.base_date)
    gu.insert(0, "기준일", a.base_date)
    seoul.insert(0, "기준일", a.base_date)

    dong.sort_values(["행정동코드", "업종대분류"]).to_csv(os.path.join(a.out, "stability_by_dong.csv"), index=False, encoding="utf-8-sig")
    gu.sort_values(["자치구", "업종대분류"]).to_csv(os.path.join(a.out, "stability_by_gu.csv"), index=False, encoding="utf-8-sig")
    seoul.to_csv(os.path.join(a.out, "stability_seoul.csv"), index=False, encoding="utf-8-sig")
    yearly(df, B=a.base_date).to_csv(os.path.join(a.out, "yearly_by_dong.csv"), index=False, encoding="utf-8-sig")

    keep = ["원천", "MGTNO", "BPLCNM", "UPTAENM", "업종대분류", "상태구분", "인허가일", "폐업일",
            "SITEWHLADDR", "RDNWHLADDR", "SITEAREA", "X", "Y", "행정동코드", "행정동명", "자치구", "좌표_자치구불일치"]
    st = df[keep].rename(columns={"MGTNO": "관리번호", "BPLCNM": "사업장명", "UPTAENM": "업태명",
                                  "SITEWHLADDR": "지번주소", "RDNWHLADDR": "도로명주소", "SITEAREA": "면적"})
    st["영업기간_일"] = (st["폐업일"].fillna(pd.Timestamp(a.base_date)) - st["인허가일"]).dt.days
    st.to_csv(os.path.join(a.out, "stores_clean.csv"), index=False, encoding="utf-8-sig")

    q["최종_업소수"] = int(len(df))
    q["업종대분류_분포"] = df["업종대분류"].value_counts().to_dict()
    with open(os.path.join(a.out, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps(q, ensure_ascii=False, indent=2, default=str))
    print(f"\n완료 → {a.out}/")


if __name__ == "__main__":
    main()
