"""
서울 인허가 데이터 정제 스크립트 (4조 '어디에 열까')

[입력] 서울 열린데이터광장 CSV 3개 + 행정동 경계 파일 1개
  --cafe        서울시 휴게음식점 인허가 정보 CSV
  --bakery      서울시 제과점영업 인허가 정보 CSV
  --restaurant  서울시 일반음식점 인허가 정보 CSV
  --dong        HangJeongDong_ver20260701.geojson (github.com/vuski/admdongkor)
  --fill        (선택) jari/dong_fill.csv. 좌표가 없는 업소의 행정동을 주소 기준으로 채움

[실행]
  python3 permits_prep.py --cafe cafe.csv --bakery bakery.csv --restaurant restaurant.csv \
      --dong HangJeongDong_ver20260701.geojson --fill ../jari/dong_fill.csv

[출력]
  1) permits_base.csv        공용 파일 (자리 팀 공유용)
                             폐업 포함, 모든 업태, 카테고리로 거르기 전 상태
  2) competition_open.csv    경쟁용: 카페/제과점/한식 + 영업중만
  3) competition_by_dong.csv 경쟁 지표: 행정동 x 카테고리별 점포 수, 면적, 밀도
  4) dong_area.csv           서울 행정동 기준표 (팀 공용)
                             adm_cd  행안부 10자리 / adm_cd8 앞 8자리(서울 생활인구 등) /
                             stat_cd 통계청 코드 / 행정동명, 구, 면적(km2)
  5) uptae_counts.csv        파일별 업태 건수 (카테고리 기준 정할 때 참고)
"""

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree

# ------------------------------------------------------------
# 카테고리 규칙 (경쟁용). 공용 파일에는 영향 없음
# ------------------------------------------------------------
CATEGORY_RULES = {
    "cafe": {"category": "카페", "uptae": ["커피숍", "다방", "전통찻집"]},
    "bakery": {"category": "제과점", "uptae": None},  # None = 전부
    "restaurant": {"category": "한식", "uptae": ["한식"], "extra": {"까페": "카페"}},
}

# 원본 컬럼 -> 통일 이름 (CSV 한글 / Open API 영문)
COLUMN_MAP = {
    "관리번호": "mgt_no", "사업장명": "name", "업태구분명": "uptae",
    "영업상태명": "status", "인허가일자": "permit_date", "폐업일자": "close_date",
    "소재지전체주소": "jibun_addr", "도로명전체주소": "road_addr",
    "지번주소": "jibun_addr", "도로명주소": "road_addr",
    "좌표정보(X)": "x", "좌표정보(Y)": "y",
    "좌표정보x(epsg5174)": "x", "좌표정보y(epsg5174)": "y",
    "최종수정시점": "updated_at", "최종수정일자": "updated_at",
    "MGTNO": "mgt_no", "BPLCNM": "name", "UPTAENM": "uptae",
    "TRDSTATENM": "status", "APVPERMYMD": "permit_date", "DCBYMD": "close_date",
    "SITEWHLADDR": "jibun_addr", "RDNWHLADDR": "road_addr",
    "X": "x", "Y": "y", "LASTMODTS": "updated_at",
}
REQUIRED = {"mgt_no", "uptae", "status", "permit_date", "x", "y"}

# 공용 파일 컬럼 (자리 팀 요청 순서)
BASE_COLUMNS = [
    "mgt_no", "name", "uptae", "permit_date", "close_date", "status",
    "jibun_addr", "road_addr", "lon", "lat", "adm_cd", "adm_nm", "dong_via",
    "gu", "source", "category", "is_open",
]


def read_csv_any_encoding(path):
    """공공데이터 CSV는 대부분 cp949(윈도우 한글). 가끔 깨진 글자가 몇 개 섞여 있어서
    그런 글자만 물음표로 바꾸고 나머지는 그대로 읽음"""
    try:
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str, low_memory=False)
    except UnicodeDecodeError:
        pass
    return pd.read_csv(path, encoding="cp949", encoding_errors="replace",
                       dtype=str, low_memory=False)


def load_one(path, kind):
    df = read_csv_any_encoding(path)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)
    df = df.loc[:, ~df.columns.duplicated()]
    missing = REQUIRED - set(df.columns)
    if missing:
        print(f"!! [{path}] 필요한 컬럼 없음: {missing}\n   실제 컬럼: {list(df.columns)}")
        sys.exit(1)
    keep = [c for c in dict.fromkeys(COLUMN_MAP.values()) if c in df.columns]
    df = df[keep].copy()
    for c in df.columns:
        df[c] = df[c].str.strip()
    df["source"] = kind
    print(f"  - {kind:<10} {len(df):>9,}건  ({path})")
    return df


def assign_category(df):
    """경쟁용 카테고리. 해당 없으면 빈칸 (공용 파일에서는 그대로 남음)"""
    df["category"] = None
    for kind, rule in CATEGORY_RULES.items():
        m = df["source"] == kind
        if rule["uptae"] is None:
            df.loc[m, "category"] = rule["category"]
        else:
            df.loc[m & df["uptae"].isin(rule["uptae"]), "category"] = rule["category"]
        for uptae, cat in rule.get("extra", {}).items():
            df.loc[m & (df["uptae"] == uptae), "category"] = cat
    return df


def load_dongs(path):
    """서울 행정동 폴리곤 + 면적(km2)"""
    with open(path, encoding="utf-8") as f:
        feats = [ft for ft in json.load(f)["features"]
                 if ft["properties"].get("sidonm", "").startswith("서울")]
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform
    geoms, rows = [], []
    for ft in feats:
        g = shape(ft["geometry"])
        p = ft["properties"]
        geoms.append(g)
        rows.append({"adm_cd": p["adm_cd2"], "adm_cd8": p["adm_cd2"][:8], "stat_cd": p["adm_cd"],
                     "adm_nm": p["adm_nm"].split()[-1],
                     "gu": p["sggnm"], "area_km2": round(shp_transform(to_m, g).area / 1e6, 4)})
    print(f"  - 서울 행정동 {len(rows)}개")
    return geoms, pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cafe"); ap.add_argument("--bakery"); ap.add_argument("--restaurant")
    ap.add_argument("--dong", required=True, help="행정동 경계 geojson")
    ap.add_argument("--fill", help="좌표가 없는 업소의 행정동 보충표 (jari/dong_fill.csv)")
    args = ap.parse_args()
    files = {k: getattr(args, k) for k in CATEGORY_RULES if getattr(args, k)}
    if not files:
        ap.print_help(); sys.exit(1)

    print("[1] 파일 읽기")
    df = pd.concat([load_one(p, k) for k, p in files.items()], ignore_index=True)
    vc = df.groupby(["source", "uptae"], dropna=False).size().reset_index(name="count")
    vc.sort_values(["source", "count"], ascending=[True, False]) \
      .to_csv("uptae_counts.csv", index=False, encoding="utf-8-sig")

    print("[2] 정제")
    addr = df["road_addr"].fillna("") if "road_addr" in df else pd.Series("", index=df.index)
    jibun = df["jibun_addr"].fillna("") if "jibun_addr" in df else pd.Series("", index=df.index)
    addr = addr.where(addr != "", jibun)
    seoul = addr.str.startswith("서울")
    print(f"  - 서울 밖/주소 없음 제외: {int((~seoul).sum()):,}건")
    df = df[seoul].copy()

    if "updated_at" in df:
        df = df.sort_values("updated_at")
    n = len(df)
    df = df.drop_duplicates(["source", "mgt_no"], keep="last")
    print(f"  - 중복 관리번호 제거: {n - len(df):,}건")

    for c in ["permit_date", "close_date"]:
        if c in df:
            df[c] = pd.to_datetime(df[c].str.replace("-", "", regex=False),
                                   format="%Y%m%d", errors="coerce")
    bad = df["close_date"].notna() & (df["close_date"] < df["permit_date"])
    df = df[~bad].copy()
    print(f"  - 폐업일 < 인허가일 이상치 제거: {int(bad.sum())}건")

    df["is_open"] = df["status"].str.contains("영업", na=False) & \
        ~df["status"].str.contains("폐업", na=False)

    print("[3] 좌표 변환 (EPSG:5174 -> 위경도)")
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    has = df["x"].notna() & df["y"].notna()
    tf = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)
    lon, lat = tf.transform(df.loc[has, "x"].values, df.loc[has, "y"].values)
    df.loc[has, "lon"] = lon
    df.loc[has, "lat"] = lat
    print(f"  - 좌표 없음: {int((~has).sum()):,}건 (아래 4-2에서 주소로 보충)")

    print("[4] 행정동 붙이기")
    geoms, dongs = load_dongs(args.dong)
    tree = STRtree(geoms)
    idx = df.index[has]
    pts = [Point(xy) for xy in zip(df.loc[idx, "lon"], df.loc[idx, "lat"])]
    hit_pt, hit_geom = tree.query(pts, predicate="within")
    match = pd.Series(hit_geom, index=idx[hit_pt])
    match = match[~match.index.duplicated()]
    df["adm_cd"] = None; df["adm_nm"] = None; df["gu"] = None
    df.loc[match.index, "adm_cd"] = dongs["adm_cd"].values[match.values]
    df.loc[match.index, "adm_nm"] = dongs["adm_nm"].values[match.values]
    df.loc[match.index, "gu"] = dongs["gu"].values[match.values]
    no_dong = has.sum() - len(match)
    print(f"  - 행정동 배정 {len(match):,}건 / 좌표는 있는데 서울 경계 밖 {int(no_dong):,}건")

    df["dong_via"] = None
    df.loc[match.index, "dong_via"] = "coord"

    # [4-2] 좌표로 못 붙인 업소는 자리 축이 주소로 찾은 행정동으로 채움
    if args.fill:
        fill = pd.read_csv(args.fill, dtype=str, encoding="utf-8-sig")
        fill = fill.drop_duplicates(["source", "mgt_no"]) \
                   .set_index(["source", "mgt_no"])[["adm_cd", "adm_nm", "gu", "via"]]
        key = pd.MultiIndex.from_frame(df[["source", "mgt_no"]])
        f = fill.reindex(key)
        f.index = df.index
        empty = df["adm_cd"].isna() & f["adm_cd"].notna()
        valid = f["adm_cd"].isin(dongs["adm_cd"])
        bad_code = int((empty & ~valid).sum())
        empty &= valid
        for c in ["adm_cd", "adm_nm", "gu"]:
            df.loc[empty, c] = f.loc[empty, c]
        df.loc[empty, "dong_via"] = f.loc[empty, "via"]
        print(f"  - 주소로 행정동 채움 {int(empty.sum()):,}건 (영업중 {int((empty & df['is_open']).sum()):,})"
              + (f" / 기준표에 없는 코드라 건너뜀 {bad_code}건" if bad_code else ""))
    print(f"  - 최종 행정동 빈칸 {int(df['adm_cd'].isna().sum()):,}건 "
          f"(영업중 {int((df['adm_cd'].isna() & df['is_open']).sum()):,})")

    # 그래도 빈 곳은 구 이름만이라도 주소에서 채움
    gu_from_addr = addr.loc[df.index].str.extract(r"^서울\S*\s+(\S+구)")[0]
    df["gu"] = df["gu"].fillna(gu_from_addr)

    df = assign_category(df)

    print("[5] 저장")
    for c in ["permit_date", "close_date"]:
        df[c] = df[c].dt.strftime("%Y-%m-%d")
    df[BASE_COLUMNS].to_csv("permits_base.csv", index=False, encoding="utf-8-sig")

    comp = df[df["category"].notna() & df["is_open"]]
    comp[BASE_COLUMNS].to_csv("competition_open.csv", index=False, encoding="utf-8-sig")

    dongs.to_csv("dong_area.csv", index=False, encoding="utf-8-sig")

    cnt = comp.dropna(subset=["adm_cd"]).groupby(["adm_cd", "category"]).size() \
        .unstack(fill_value=0).reindex(dongs["adm_cd"], fill_value=0)
    by = dongs[["adm_cd", "adm_nm", "gu", "area_km2"]].set_index("adm_cd").join(cnt).reset_index()
    for cat in ["카페", "제과점", "한식"]:
        if cat not in by:
            by[cat] = 0
        by[f"{cat}_밀도(개/km2)"] = (by[cat] / by["area_km2"]).round(1)
    by.to_csv("competition_by_dong.csv", index=False, encoding="utf-8-sig")

    print("\n[완료]")
    print(f"  permits_base.csv        {len(df):>9,}건 (영업중 {int(df['is_open'].sum()):,} / 폐업 등 {int((~df['is_open']).sum()):,})")
    print(f"  competition_open.csv    {len(comp):>9,}건")
    print(comp["category"].value_counts().to_string())
    print(f"  competition_by_dong.csv {len(by):>9,}개 행정동")


if __name__ == "__main__":
    main()
