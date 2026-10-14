"""
교차검증: API 수집본으로 낸 결과와 '내려받은 CSV'로 낸 결과를 비교한다.
(선택) 경쟁 축(competition/competition_by_dong.csv)의 영업 중 점포 수와도 비교한다.

사용법
  python build_stability.py --out out_api
  python build_stability.py --out out_dl --restaurant-file 다운로드_일반음식점.csv --cafe-file 다운로드_휴게음식점.csv
  python compare_sources.py out_api out_dl --competition ../competition/competition_by_dong.csv

결과: 화면 출력 + out_api/compare_report.md
두 결과는 같은 --base-date 로 만들어야 비교가 의미 있다.
"""
import argparse
import os

import pandas as pd

KEY = ["원천", "관리번호"]


def md(df):
    """tabulate 없이 마크다운 표 만들기"""
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(out)


def load_stores(d):
    s = pd.read_csv(os.path.join(d, "stores_clean.csv"), dtype=str).fillna("")
    return s.drop_duplicates(KEY)


def record_check(a, b, lines):
    lines.append("## 1. 업소 단위 비교 (stores_clean.csv)\n")
    lines.append("| 원천 | A만 | B만 | 공통 | 상태 불일치 | 인허가일 불일치 | 폐업일 불일치 | 행정동 불일치 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    samples = []
    for src in sorted(set(a["원천"]) | set(b["원천"])):
        aa, bb = a[a["원천"] == src], b[b["원천"] == src]
        m = aa.merge(bb, on=KEY, suffixes=("_a", "_b"))
        only_a = len(aa) - len(m)
        only_b = len(bb) - len(m)
        diff = {c: (m[f"{c}_a"] != m[f"{c}_b"]) for c in ["상태구분", "인허가일", "폐업일", "행정동코드"]}
        pct = lambda s: f"{int(s.sum()):,} ({s.mean():.2%})" if len(s) else "0"
        lines.append(f"| {src} | {only_a:,} | {only_b:,} | {len(m):,} | {pct(diff['상태구분'])} | "
                     f"{pct(diff['인허가일'])} | {pct(diff['폐업일'])} | {pct(diff['행정동코드'])} |")
        any_diff = diff["상태구분"] | diff["인허가일"] | diff["폐업일"] | diff["행정동코드"]
        cols = KEY + [f"{c}_{s}" for c in ["상태구분", "인허가일", "폐업일", "행정동코드"] for s in "ab"]
        samples.append(m.loc[any_diff, cols].head(5))
    smp = pd.concat(samples)
    if len(smp):
        lines.append("\n불일치 예시 (원천별 최대 5건)\n")
        lines.append(md(smp))
    lines.append("")


def metric_check(da, db, lines):
    lines.append("## 2. 지표 비교 (stability_by_dong.csv)\n")
    a = pd.read_csv(os.path.join(da, "stability_by_dong.csv"), dtype={"행정동코드": str})
    b = pd.read_csv(os.path.join(db, "stability_by_dong.csv"), dtype={"행정동코드": str})
    m = a.merge(b, on=["행정동코드", "업종대분류"], suffixes=("_a", "_b"))
    lines.append("| 업종 | 영업중 차이 합 | 영업중 최대차 | 교체율 최대차(%p) | 생존율 최대차(%p) |")
    lines.append("|---|---:|---:|---:|---:|")
    for cat, g in m.groupby("업종대분류"):
        d_open = (g["영업중_현재_a"] - g["영업중_현재_b"]).abs()
        d_c = (g["교체율_a"] - g["교체율_b"]).abs() * 100
        d_s = (g["3년_생존율_a"] - g["3년_생존율_b"]).abs() * 100
        lines.append(f"| {cat} | {int(d_open.sum()):,} | {int(d_open.max())} | "
                     f"{d_c.max():.2f} | {d_s.max():.2f} |")
    m["영업중_차이"] = (m["영업중_현재_a"] - m["영업중_현재_b"]).abs()
    top = m.sort_values("영업중_차이", ascending=False).head(10)
    lines.append("\n영업중 업소 수 차이가 큰 행정동×업종 상위 10\n")
    lines.append(md(top[["행정동명_a", "자치구_a", "업종대분류", "영업중_현재_a", "영업중_현재_b", "영업중_차이"]]
                 .rename(columns={"행정동명_a": "행정동명", "자치구_a": "자치구"})))
    lines.append("")


def competition_check(da, comp_path, lines):
    lines.append("## 3. 경쟁 축과 비교 (영업 중 점포 수)\n")
    lines.append("업종 정의가 달라 완전히 같을 수는 없다. 경쟁 축 카페 = 커피숍·다방·전통찻집·까페, "
                 "안정성 카페는 떡카페·키즈카페도 포함. 한식은 두 축 모두 업태 '한식' 중심이나 "
                 "안정성은 냉면·탕류·식육·횟집도 한식으로 묶는다. **방향(상관)이 맞는지**를 본다.\n")
    a = pd.read_csv(os.path.join(da, "stability_by_dong.csv"), dtype={"adm_cd": str})
    c = pd.read_csv(comp_path, dtype={"adm_cd": str})
    lines.append("| 업종 | 행정동 수 | 안정성 합계 | 경쟁 합계 | 상관계수 | 차이 중앙값 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat in ["카페", "한식"]:
        if cat not in c.columns:
            continue
        s = a[a["업종대분류"] == cat][["adm_cd", "영업중_현재"]]
        m = s.merge(c[["adm_cd", cat]], on="adm_cd")
        corr = m["영업중_현재"].corr(m[cat])
        med = (m["영업중_현재"] - m[cat]).abs().median()
        lines.append(f"| {cat} | {len(m)} | {int(m['영업중_현재'].sum()):,} | {int(m[cat].sum()):,} | "
                     f"{corr:.3f} | {med:.0f} |")
    lines.append("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", help="기준 결과 폴더 (예: out_api)")
    ap.add_argument("b", nargs="?", help="비교 결과 폴더 (예: out_dl)")
    ap.add_argument("--competition", help="competition/competition_by_dong.csv 경로")
    x = ap.parse_args()

    lines = [f"# 교차검증 리포트\n\nA = `{x.a}`" + (f", B = `{x.b}`" if x.b else "") + "\n"]
    if x.b:
        record_check(load_stores(x.a), load_stores(x.b), lines)
        metric_check(x.a, x.b, lines)
    if x.competition:
        competition_check(x.a, x.competition, lines)
    text = "\n".join(lines)
    path = os.path.join(x.a, "compare_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
