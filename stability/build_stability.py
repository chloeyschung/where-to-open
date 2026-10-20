"""
안정성 축 집계: 서울 행정동 427 × 업종 3 (카페·제과점·한식)  — 공통 규칙(docs/common-rules.md) 적용판

입력
  data/base/permits_base.csv   팀 공용 파일 (competition/permits_prep.py 결과, 드라이브 공유. git 에는 안 올라감)
  competition/dong_area.csv    서울 행정동 기준표 427개 (adm_cd 10자리가 키)

출력 (기본 stability/data/ — 이 4개만 커밋)
  stability_by_dong.csv     행정동 × 업종 지표 (메인)
  stability_by_gu.csv       자치구 × 업종 지표 (구 평균 대체에 쓰는 값)
  stability_seoul.csv       서울 전체 × 업종 지표 (비교 기준선)
  quality_report.json       제외 사유별 건수, 지표별 구 평균 대체 건수
  (--extra-out 폴더에 yearly_by_dong.csv: 행정동 × 업종 × 연도 신규·폐업 — 지금은 쓰지 않음, 커밋 안 함)

공통 규칙 적용
  1  공용 파일만 쓴다. 업소 키 = source + mgt_no, 행정동 = adm_cd (주소로 이미 채워짐)
  2  기준일 2026-09-30. 기준일 뒤 인허가는 빼고, 기준일 뒤 폐업한 가게는 기준일에 영업 중으로 센다
  3  업종은 category 열 3개 (카페·제과점·한식). category 가 빈 업소는 쓰지 않는다
  4  close_date_missing = True 는 모든 계산에서 뺀다 (신규_1년 포함 → 분자·분모가 같은 묶음)
  5  is_temp = True(팝업·행사) 는 뺀다. temp_rule 로 다시 판정하지 않고 열을 그대로 쓴다
  6  주인만 바뀐 가게를 합치지 않는다 (관리번호 단위)
  7  지표마다 따로: 교체율·신규율은 영업중_기초, 3년 생존율은 3년_코호트가 20곳 미만이면 그 지표만 구 평균

지표 정의 (기준일 B)
  영업중_기초   = B-1년 시점에 영업 중이던 업소 수
  영업중_현재   = B 시점에 영업 중인 업소 수
  신규_1년      = (B-1년, B] 에 인허가된 업소 수
  폐업_1년      = (B-1년, B] 에 폐업한 업소 수
  교체율        = 폐업_1년 / 영업중_기초
  신규율        = 신규_1년 / 영업중_기초     (교체율과 항상 나란히 본다)
  3년_코호트    = [B-8년, B-3년] 에 인허가된 업소 수
  3년_생존      = 그중 영업 중이거나, 폐업했어도 영업기간이 3년 이상인 업소 수
  3년_생존율    = 3년_생존 / 3년_코호트

영업상태 처리
  폐업            → 폐업일(close_date) 기준
  영업/정상·휴업  → 영업 중 (폐업일이 찍혀 있어도 데이터 오류로 보고 무시, 건수는 리포트)
  취소·말소·정지 등 → 행정처분이라 창업·폐업 흐름과 달라 제외

사용법 (저장소 루트에서)
  python stability/build_stability.py
  python stability/build_stability.py --base data/base/permits_base.csv --base-date 2026-09-30
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
CATEGORIES = ["카페", "제과점", "한식"]
METRICS = {  # 지표 → (분자, 분모)
    "교체율": ("폐업_1년", "영업중_기초"),
    "신규율": ("신규_1년", "영업중_기초"),
    "3년_생존율": ("3년_생존", "3년_코호트"),
}
COUNTS = ["영업중_기초", "영업중_현재", "신규_1년", "폐업_1년", "3년_코호트", "3년_생존"]
BASE_COLUMNS = ["source", "mgt_no", "permit_date", "close_date", "status", "adm_cd", "gu",
                "category", "close_date_missing", "is_temp"]


# ---------------------------------------------------------------- 읽기 · 정제
def to_bool(s):
    return s.astype("string").str.strip().str.lower().isin(["true", "1", "t", "y", "yes"])


def to_date(s):
    digits = s.astype("string").str.replace(r"[^0-9]", "", regex=True).str.slice(0, 8)
    return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")


def load_base(path, base_date, q):
    if not os.path.exists(path):
        raise SystemExit(f"\n공용 파일이 없습니다: {path}\n"
                         "드라이브에서 permits_base.csv 를 받아 data/base/ 에 두세요 (docs/common-rules.md 규칙 1).")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False)
    missing = set(BASE_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit(f"\n공용 파일에 필요한 열이 없습니다: {sorted(missing)}\n"
                         "is_temp·close_date_missing 이 들어간 새 공용 파일인지 확인하세요.")
    df = df[BASE_COLUMNS].copy()
    for c in ["source", "mgt_no", "status", "adm_cd", "gu", "category"]:
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    B = pd.Timestamp(base_date)
    q["입력_건수"] = int(len(df))
    q["원천별_건수"] = {k: int(v) for k, v in df["source"].value_counts().items()}

    dup = df.duplicated(["source", "mgt_no"], keep="last")
    q["중복_업소키(source+mgt_no)_제외"] = int(dup.sum())
    df = df[~dup]

    df["is_temp"] = to_bool(df["is_temp"])
    df["close_date_missing"] = to_bool(df["close_date_missing"])
    df["인허가일"] = to_date(df["permit_date"])
    df["폐업일"] = to_date(df["close_date"])
    st = df["status"].fillna("")
    df["상태구분"] = np.select([st.str.contains("폐업"), st.str.contains("영업|정상|휴업")],
                           ["폐업", "영업"], default="행정처분등")

    steps = [  # (사유, 제외 조건) — 앞 단계에서 빠진 건은 뒤에서 다시 세지 않는다
        ("업종_해당없음(category 빈칸)", ~df["category"].isin(CATEGORIES).fillna(False)),
        ("팝업·행사(is_temp)", df["is_temp"]),
        ("폐업일_없음(close_date_missing)", df["close_date_missing"]),
        ("행정처분등_영업상태", df["상태구분"] == "행정처분등"),
        ("인허가일_없음", df["인허가일"].isna()),
        (f"기준일({base_date})_뒤_인허가", df["인허가일"] > B),
    ]
    excluded, keep = {}, pd.Series(True, index=df.index)
    for name, cond in steps:
        hit = keep & cond.fillna(False).astype(bool)
        excluded[name] = int(hit.sum())
        keep &= ~hit
    df = df[keep].copy()

    # 영업 중인데 폐업일이 찍힌 데이터 오류 → 폐업일 무시
    bad_close = (df["상태구분"] != "폐업") & df["폐업일"].notna()
    df.loc[bad_close, "폐업일"] = pd.NaT
    # 폐업인데 폐업일을 못 읽은 경우(close_date_missing 이 놓친 형식 오류)도 날짜 계산에서 뺀다
    unreadable = (df["상태구분"] == "폐업") & df["폐업일"].isna()
    excluded["폐업일_형식오류"] = int(unreadable.sum())
    df = df[~unreadable]
    bad_order = df["폐업일"].notna() & (df["폐업일"] < df["인허가일"])
    excluded["폐업일<인허가일"] = int(bad_order.sum())
    df = df[~bad_order].copy()

    q["제외"] = excluded
    q["영업중인데_폐업일_무시"] = int(bad_close.sum())
    q["계산_대상_업소"] = int(len(df))
    q["업종별_계산_대상"] = {k: int(v) for k, v in df["category"].value_counts().reindex(CATEGORIES, fill_value=0).items()}
    q["기준일_뒤_폐업(기준일엔_영업중으로_셈)"] = int((df["폐업일"] > B).sum())
    q["행정동_없음(서울·구 지표에만 포함)"] = int(df["adm_cd"].isna().sum())
    q["자치구_없음(서울 지표에만 포함)"] = int(df["gu"].isna().sum())
    return df


# ---------------------------------------------------------------- 지표 계산
def count_flags(df, base_date):
    B = pd.Timestamp(base_date)
    B1 = B - pd.DateOffset(years=1)
    c_lo, c_hi = B - pd.DateOffset(years=8), B - pd.DateOffset(years=3)
    o, c = df["인허가일"], df["폐업일"]

    def alive(t):
        return (o <= t) & (c.isna() | (c > t))

    cohort = (o >= c_lo) & (o <= c_hi)
    return pd.DataFrame({
        "영업중_기초": alive(B1),
        "영업중_현재": alive(B),
        "신규_1년": (o > B1) & (o <= B),
        "폐업_1년": c.notna() & (c > B1) & (c <= B),
        "3년_코호트": cohort,
        "3년_생존": cohort & (c.isna() | (c >= o + pd.DateOffset(years=3))),
    }, index=df.index).astype(int)


def aggregate(df, flags, keys, min_n):
    agg = pd.concat([df[keys], flags], axis=1).groupby(keys, dropna=True).sum().reset_index()
    for m, (num, den) in METRICS.items():
        agg[m] = (agg[num] / agg[den].replace(0, np.nan)).where(agg[den] >= min_n).round(4)
    return agg


def with_fallback(dong, gu):
    """공통 규칙 7: 지표마다 따로 구 평균으로 대체하고 지표별로 표시"""
    g = gu[["gu", "category"] + list(METRICS)].rename(columns={m: f"구_{m}" for m in METRICS})
    out = dong.merge(g, on=["gu", "category"], how="left")
    for m in METRICS:
        own, alt = out[m], out[f"구_{m}"]
        out[f"표시_{m}"] = own.fillna(alt)
        out[f"{m}_기준"] = np.select([own.notna(), alt.notna()], ["행정동", "구 평균"], default="없음")
    return out.drop(columns=[f"구_{m}" for m in METRICS])


def yearly(df, years=10, base_date=None):
    B = pd.Timestamp(base_date)
    y0 = B.year - years + 1
    d = df[df["adm_cd"].notna()]
    keys = ["adm_cd", "category"]
    o = d.assign(연도=d["인허가일"].dt.year)
    o = o[o["연도"] >= y0].groupby(keys + ["연도"]).size().rename("신규")
    c = d[d["폐업일"].notna() & (d["폐업일"] <= B)].assign(연도=lambda x: x["폐업일"].dt.year)
    c = c[c["연도"] >= y0].groupby(keys + ["연도"]).size().rename("폐업")
    out = pd.concat([o, c], axis=1).fillna(0).astype(int).reset_index()
    out["순증"] = out["신규"] - out["폐업"]
    return out.sort_values(keys + ["연도"])


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="안정성 축 집계 (공통 규칙 적용)")
    ap.add_argument("--base", default=os.path.join(ROOT, "data", "base", "permits_base.csv"), help="공용 파일")
    ap.add_argument("--dongs", default=os.path.join(ROOT, "competition", "dong_area.csv"), help="행정동 기준표")
    ap.add_argument("--out", default=os.path.join(HERE, "data"), help="결과 4개 파일 폴더")
    ap.add_argument("--extra-out", default=os.path.join(HERE, "out"), help="커밋 안 하는 보조 결과 폴더")
    ap.add_argument("--base-date", default="2026-09-30", help="기준일 (공통 규칙 2)")
    ap.add_argument("--min-n", type=int, default=20, help="동네 값을 쓰는 최소 가게 수 (공통 규칙 7)")
    a = ap.parse_args()
    q = {"기준일": a.base_date, "최소표본": a.min_n, "입력": os.path.basename(a.base)}

    print("[1/3] 공용 파일 읽기·정제")
    df = load_base(a.base, a.base_date, q)
    print(f"  계산 대상 {len(df):,}건 (" + ", ".join(f"{k} {v:,}" for k, v in q["업종별_계산_대상"].items()) + ")")
    print("  제외: " + ", ".join(f"{k} {v:,}" for k, v in q["제외"].items() if v))

    print("[2/3] 지표 계산")
    flags = count_flags(df, a.base_date)
    seoul = aggregate(df.assign(범위="서울"), flags, ["범위", "category"], a.min_n)
    has_gu, has_dong = df["gu"].notna(), df["adm_cd"].notna()
    gu = aggregate(df[has_gu], flags[has_gu], ["gu", "category"], a.min_n)
    dong = aggregate(df[has_dong], flags[has_dong], ["adm_cd", "category"], a.min_n)

    dongs = pd.read_csv(a.dongs, dtype=str)[["adm_cd", "adm_cd8", "adm_nm", "gu"]]
    unknown = sorted(set(dong["adm_cd"]) - set(dongs["adm_cd"]))
    q["기준표에_없는_adm_cd"] = unknown
    grid = dongs.merge(pd.DataFrame({"category": CATEGORIES}), how="cross")
    dong = grid.merge(dong, on=["adm_cd", "category"], how="left")
    dong[COUNTS] = dong[COUNTS].fillna(0).astype(int)
    dong = with_fallback(dong, gu)
    q["지표별_값_기준"] = {m: {k: int(v) for k, v in dong[f"{m}_기준"].value_counts().items()} for m in METRICS}

    print("[3/3] 저장")
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.extra_out, exist_ok=True)
    for t in (dong, gu, seoul):
        t.insert(0, "기준일", a.base_date)
    order = ["기준일", "adm_cd", "adm_cd8", "adm_nm", "gu", "category"] + COUNTS + list(METRICS) \
        + [c for m in METRICS for c in (f"표시_{m}", f"{m}_기준")]
    dong[order].sort_values(["adm_cd", "category"]).to_csv(
        os.path.join(a.out, "stability_by_dong.csv"), index=False, encoding="utf-8-sig")
    gu.sort_values(["gu", "category"]).to_csv(os.path.join(a.out, "stability_by_gu.csv"), index=False, encoding="utf-8-sig")
    seoul.to_csv(os.path.join(a.out, "stability_seoul.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(a.out, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    yearly(df, base_date=a.base_date).to_csv(os.path.join(a.extra_out, "yearly_by_dong.csv"),
                                             index=False, encoding="utf-8-sig")

    print(json.dumps(q, ensure_ascii=False, indent=2))
    print(f"\n완료 → {a.out}/ (결과 4개), {a.extra_out}/yearly_by_dong.csv")


if __name__ == "__main__":
    main()
