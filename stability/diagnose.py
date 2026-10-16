"""
품질 진단: stores_clean.csv 에서 작은 요약표 3개를 만든다 (공유·검토용)

  python diagnose.py                 # out_api/stores_clean.csv 사용
  python diagnose.py --out out_api

결과 (out_api/diag/)
  diag_lifetime.csv        업종별 '단기 영업' 비율 (팝업·행사성 인허가 판별용)
  diag_hot_buildings.csv   최근 3년 인허가가 몰린 건물 상위 50 (백화점·복합몰 팝업 의심)
  diag_missing_coords.csv  개업연도·영업상태별 좌표 누락 비율 (지표 왜곡 여부)
"""
import argparse
import os

import pandas as pd

from temp_rule import jibun_key


def building_key(addr):
    """건물(지번) 단위 키 — 팝업 판정(temp_rule)과 같은 jibun_key 를 쓴다"""
    return addr.fillna("").map(jibun_key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out_api")
    ap.add_argument("--since", default="2021-01-01", help="최근 인허가 기준 시작일")
    a = ap.parse_args()
    s = pd.read_csv(os.path.join(a.out, "stores_clean.csv"), dtype=str, low_memory=False).fillna("")
    s["인허가일"] = pd.to_datetime(s["인허가일"], errors="coerce")
    s["폐업일"] = pd.to_datetime(s["폐업일"], errors="coerce")
    s["영업기간_일"] = pd.to_numeric(s["영업기간_일"], errors="coerce")
    s["폐업"] = s["상태구분"] == "폐업"
    d = os.path.join(a.out, "diag")
    os.makedirs(d, exist_ok=True)

    # 1) 업종별 단기 영업 비율 — 최근 개업분 중 폐업한 업소의 영업기간
    since = pd.Timestamp(a.since)
    r = s[(s["인허가일"] >= since)]
    rows = []
    for (src, cat), g in r.groupby(["원천", "업종대분류"]):
        c = g[g["폐업"]]
        rows.append({
            "원천": src, "업종대분류": cat, "최근개업": len(g), "그중_폐업": len(c),
            "30일이내_폐업": int((c["영업기간_일"] <= 30).sum()),
            "90일이내_폐업": int((c["영업기간_일"] <= 90).sum()),
            "1년이내_폐업": int((c["영업기간_일"] <= 365).sum()),
            "90일이내_비율(최근개업대비)": round((c["영업기간_일"] <= 90).sum() / max(len(g), 1), 4),
        })
    # 업태 단위로도 (기타가 무엇인지 보려고)
    for (src, up), g in r[r["업종대분류"] == "기타"].groupby(["원천", "업태명"]):
        c = g[g["폐업"]]
        rows.append({
            "원천": src, "업종대분류": f"기타 / {up or '(빈칸)'}", "최근개업": len(g), "그중_폐업": len(c),
            "30일이내_폐업": int((c["영업기간_일"] <= 30).sum()),
            "90일이내_폐업": int((c["영업기간_일"] <= 90).sum()),
            "1년이내_폐업": int((c["영업기간_일"] <= 365).sum()),
            "90일이내_비율(최근개업대비)": round((c["영업기간_일"] <= 90).sum() / max(len(g), 1), 4),
        })
    pd.DataFrame(rows).sort_values("90일이내_비율(최근개업대비)", ascending=False) \
        .to_csv(os.path.join(d, "diag_lifetime.csv"), index=False, encoding="utf-8-sig")

    # 2) 최근 인허가가 몰린 건물
    r = r.assign(건물=building_key(r["지번주소"]))
    r = r[r["건물"].notna()]
    out = []
    for b, g in r.groupby("건물"):
        if len(g) < 30:
            continue
        c = g[g["폐업"]]
        out.append({
            "건물(지번)": b, "행정동명": g["행정동명"].mode().iat[0] if g["행정동명"].ne("").any() else "",
            "최근인허가": len(g), "영업중": int((~g["폐업"]).sum()),
            "90일이내_폐업": int((c["영업기간_일"] <= 90).sum()),
            "영업기간_중앙값(일,폐업분)": int(c["영업기간_일"].median()) if len(c) else None,
            "주요업태": " / ".join(f"{k}({v})" for k, v in g["업태명"].value_counts().head(3).items()),
            "사업장명_예시": " / ".join(g["사업장명"].drop_duplicates().head(6)),
        })
    cols = ["건물(지번)", "행정동명", "최근인허가", "영업중", "90일이내_폐업", "영업기간_중앙값(일,폐업분)", "주요업태", "사업장명_예시"]
    pd.DataFrame(out, columns=cols).sort_values("최근인허가", ascending=False).head(50) \
        .to_csv(os.path.join(d, "diag_hot_buildings.csv"), index=False, encoding="utf-8-sig")

    # 3) 좌표 누락
    s["개업연도구간"] = pd.cut(s["인허가일"].dt.year, [0, 1999, 2009, 2014, 2017, 2020, 2023, 2100],
                          labels=["~1999", "2000-09", "2010-14", "2015-17", "2018-20", "2021-23", "2024~"])
    s["좌표누락"] = s["행정동코드"] == ""
    m = s.groupby(["개업연도구간", "상태구분"], observed=True).agg(전체=("좌표누락", "size"), 좌표누락=("좌표누락", "sum")).reset_index()
    m["누락비율"] = (m["좌표누락"] / m["전체"]).round(4)
    m.to_csv(os.path.join(d, "diag_missing_coords.csv"), index=False, encoding="utf-8-sig")

    print(f"완료 → {d}/")
    for f in sorted(os.listdir(d)):
        print("  ", f)


if __name__ == "__main__":
    main()
