"""build_stability.py 검증 — 공용 파일(permits_base.csv) 형식 합성 데이터로 공통 규칙과 지표를 확인한다.
실행: python stability/tests/test_build_stability.py   (pandas 만 필요)
"""
import datetime as dt
import json
import os
import random
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(ROOT, "stability", "build_stability.py")
DONGS = os.path.join(ROOT, "competition", "dong_area.csv")
B = dt.date(2026, 9, 30)
COLS = ["mgt_no", "name", "uptae", "permit_date", "close_date", "status", "jibun_addr", "road_addr", "lon", "lat",
        "adm_cd", "adm_nm", "dong_via", "gu", "source", "category", "is_open", "close_date_missing", "is_temp"]
SRC = {"카페": "cafe", "제과점": "bakery", "한식": "restaurant"}


def make_base(path, seed=7):
    random.seed(seed)
    dongs = pd.read_csv(DONGS, dtype=str)
    busy = dongs.iloc[:3]                     # 가게를 몰아줄 동 3곳 (동네 값이 나오게)
    rows = []

    def add(mgt, cat, d, opened, closed=None, status=None, **kw):
        r = {c: "" for c in COLS}
        r.update(mgt_no=mgt, name=f"가게{mgt}", uptae=cat, permit_date=opened, close_date=closed or "",
                 status=status or ("폐업" if closed else "영업/정상"), adm_cd=d["adm_cd"], adm_nm=d["adm_nm"],
                 gu=d["gu"], source=SRC.get(cat, "restaurant"), category=cat if cat in SRC else "",
                 close_date_missing="False", is_temp="False")
        r.update(kw)
        rows.append(r)

    n = 0
    for _, d in dongs.iterrows():
        k = 220 if d["adm_cd"] in set(busy["adm_cd"]) else random.randint(0, 25)
        for _ in range(k):
            n += 1
            cat = random.choice(["카페", "제과점", "한식", "한식"])
            o = dt.date(2008, 1, 1) + dt.timedelta(days=random.randint(0, 6800))
            if random.random() < 0.45:
                c = o + dt.timedelta(days=random.randint(20, 3500))
                add(f"m{n}", cat, d, o.isoformat(), c.isoformat())
            else:
                add(f"m{n}", cat, d, o.isoformat(), status=random.choice(["영업/정상", "영업/정상", "휴업"]))
    d0 = busy.iloc[0]
    # 규칙 확인용 특수 행 (관리번호로 찾는다)
    add("x_temp", "카페", d0, "2026-03-01", "2026-03-20", is_temp="True")            # 규칙 5: 빠짐
    add("x_missing", "카페", d0, "2026-02-01", None, status="폐업", close_date_missing="True")  # 규칙 4: 신규에서도 빠짐
    add("x_after", "카페", d0, "2026-10-05")                                          # 규칙 2: 기준일 뒤 인허가
    add("x_closeafter", "카페", d0, "2024-01-01", "2026-10-08")                       # 규칙 2: 9/30엔 영업 중
    add("x_nocat", "기타", d0, "2025-12-01")                                          # 규칙 3: category 빈칸
    add("x_cancel", "한식", d0, "2025-12-01", status="취소/말소/만료/정지/중지")        # 행정처분
    add("x_openclose", "한식", d0, "2020-01-01", "2026-01-01", status="영업/정상")    # 영업 중인데 폐업일 → 무시
    add("x_nodong", "한식", d0, "2025-11-01", adm_cd="", adm_nm="")                   # 행정동 없음 → 구·서울만
    add("x_dup", "한식", d0, "2025-11-02")                                            # 같은 source+mgt_no 중복
    add("x_dup", "한식", d0, "2025-11-02")
    add("x_dup", "카페", d0, "2025-11-03", source="cafe")                             # 다른 source 같은 번호 → 별개
    pd.DataFrame(rows)[COLS].to_csv(path, index=False, encoding="utf-8-sig")
    return pd.DataFrame(rows)


def recompute(base, adm_cd, cat):
    """규칙을 처음부터 다시 적용해 한 행정동·업종의 6개 건수를 센다 (build 코드와 독립)"""
    B1, lo, hi = dt.date(2025, 9, 30), dt.date(2018, 9, 30), dt.date(2023, 9, 30)
    P = lambda s: dt.date.fromisoformat(s) if isinstance(s, str) and s else None
    seen, e = set(), dict(a0=0, a1=0, n=0, c=0, co=0, sv=0)
    for r in base.itertuples():
        key = (r.source, r.mgt_no)
        if key in seen:
            continue
        seen.add(key)
        if r.adm_cd != adm_cd or r.category != cat or r.is_temp == "True" or r.close_date_missing == "True":
            continue
        if "폐업" in r.status:
            closed = True
        elif any(w in r.status for w in ("영업", "정상", "휴업")):
            closed = False
        else:
            continue
        o, c = P(r.permit_date), (P(r.close_date) if closed else None)
        if o is None or o > B or (c and c < o):
            continue
        e["a0"] += o <= B1 and (c is None or c > B1)
        e["a1"] += o <= B and (c is None or c > B)
        e["n"] += B1 < o <= B
        e["c"] += bool(c and B1 < c <= B)
        if lo <= o <= hi:
            e["co"] += 1
            try:
                o3 = o.replace(year=o.year + 3)
            except ValueError:
                o3 = o.replace(year=o.year + 3, day=28)
            e["sv"] += c is None or c >= o3
    return e


def main():
    tmp = tempfile.mkdtemp(prefix="stab_test_")
    base_path = os.path.join(tmp, "permits_base.csv")
    base = make_base(base_path)
    r = subprocess.run([sys.executable, BUILD, "--base", base_path, "--out", os.path.join(tmp, "data"),
                        "--extra-out", os.path.join(tmp, "out")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = os.path.join(tmp, "data")
    d = pd.read_csv(os.path.join(out, "stability_by_dong.csv"), dtype={"adm_cd": str, "adm_cd8": str})
    gu = pd.read_csv(os.path.join(out, "stability_by_gu.csv"))
    q = json.load(open(os.path.join(out, "quality_report.json"), encoding="utf-8"))

    # 형태: 427동 × 3업종, 기준일 9/30
    assert len(d) == 427 * 3 and set(d["category"]) == {"카페", "제과점", "한식"}, len(d)
    assert set(d["기준일"]) == {"2026-09-30"}
    print("ok  427동 × 3업종, 기준일 2026-09-30")

    # 제외 규칙
    ex = q["제외"]
    assert ex["팝업·행사(is_temp)"] == 1 and ex["폐업일_없음(close_date_missing)"] == 1
    assert ex["기준일(2026-09-30)_뒤_인허가"] == 1 and ex["업종_해당없음(category 빈칸)"] == 1
    assert ex["행정처분등_영업상태"] == 1 and q["중복_업소키(source+mgt_no)_제외"] == 1
    uniq = base.drop_duplicates(["source", "mgt_no"])
    after_close = int(((uniq["close_date"] > "2026-09-30") & uniq["category"].ne("") & uniq["status"].str.contains("폐업")
                       & uniq["is_temp"].eq("False")).sum())
    assert q["영업중인데_폐업일_무시"] == 1 and q["기준일_뒤_폐업(기준일엔_영업중으로_셈)"] == after_close, after_close
    assert q["행정동_없음(서울·구 지표에만 포함)"] == 1
    print("ok  제외 규칙 (is_temp, close_date_missing, 기준일 뒤 인허가, category, 행정처분, 중복키)")

    # 독립 재계산 — 특수 행이 몰린 동 포함 30개
    d0 = pd.read_csv(DONGS, dtype=str).iloc[0]["adm_cd"]
    sample = pd.concat([d[d["adm_cd"] == d0], d[d["영업중_현재"] > 0].sample(27, random_state=3)])
    bad = 0
    for row in sample.itertuples():
        e = recompute(base, row.adm_cd, row.category)
        g = dict(a0=row.영업중_기초, a1=row.영업중_현재, n=row.신규_1년, c=row.폐업_1년, co=row._11, sv=row._12)
        if e != g:
            bad += 1
            print("MISMATCH", row.adm_cd, row.category, e, g)
    assert bad == 0
    print(f"ok  독립 재계산 {len(sample)}개 행 일치 (리뷰 3번: close_date_missing 은 신규에서도 빠짐)")

    # 행정동 없는 업소: 동 합계 < 구 합계
    gsum = gu[(gu["gu"] == pd.read_csv(DONGS, dtype=str).iloc[0]["gu"]) & (gu["category"] == "한식")]["신규_1년"].iat[0]
    dsum = d[(d["gu"] == pd.read_csv(DONGS, dtype=str).iloc[0]["gu"]) & (d["category"] == "한식")]["신규_1년"].sum()
    assert gsum == dsum + 1, (gsum, dsum)
    print("ok  행정동 없는 업소는 구 지표에만 포함")

    # 지표별 구 평균 (리뷰 4번)
    for m, den in [("교체율", "영업중_기초"), ("신규율", "영업중_기초"), ("3년_생존율", "3년_코호트")]:
        own = d[d[den] >= 20]
        assert (own[f"{m}_기준"] == "행정동").all() and (own[f"표시_{m}"] == own[m]).all()
        low = d[(d[den] < 20)].merge(gu[["gu", "category", m]].rename(columns={m: "g"}), on=["gu", "category"])
        assert low[m].isna().all()
        assert (low.loc[low["g"].notna(), f"{m}_기준"] == "구 평균").all()
        assert (low.loc[low["g"].notna(), f"표시_{m}"] == low.loc[low["g"].notna(), "g"]).all()
    mixed = d[(d["영업중_기초"] >= 20) & (d["3년_코호트"] < 20)]
    assert len(mixed) and (mixed["교체율_기준"] == "행정동").all() and (mixed["3년_생존율_기준"] != "행정동").all()
    print(f"ok  지표별 구 평균 대체 (교체율은 동네 값·생존율만 구 평균인 행 {len(mixed)}개 확인)")
    print("전체 통과")


if __name__ == "__main__":
    main()
