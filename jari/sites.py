"""자리 지표를 계산한다.

자리 = 같은 지번(구 동 번지). 층·호는 구분하지 않는다.
입력: data/base/permits_base.csv (경쟁 축 공용 파일), jari/dong_fill.csv (fill_dong.py)
출력: data/seoul/sites.csv (자리별 지표), data/seoul/site_history.csv (자리별 가게 이력)

규칙
- 같은 자리 + 같은 상호 + 폐업 30일 전 ~ 폐업 후 90일 안에 다시 인허가 → 한 가게로 합친다
  (주인 변경·업종 전환 때 관리번호가 새로 나오기 때문. 새 허가가 옛 허가 폐업 신고보다 먼저 나는 경우가 있어 30일 겹침을 허용)
- 상태는 폐업인데 폐업일이 빈 업소는 언제 닫았는지 몰라 뺀다
- 백화점·행사 팝업(공용 파일 is_temp)은 뺀다
- 기준일(BASE) 뒤에 난 인허가는 빼고, 기준일 뒤에 폐업한 가게는 기준일에 영업 중으로 본다
- 최근 10년 안에 영업한 가게가 하나라도 있는 자리만 남긴다
- 최대 동시 영업 수가 2 이상이면 여러 점포 건물로 보고, 한 칸당 교체 횟수로 비교한다
"""
import csv, os, statistics as S, collections as C
from datetime import date
from common import ROOT, DATA, CUT, BASE, jibun_key

MERGE_DAYS = (-30, 90)            # 폐업일 기준 재인허가 허용 범위


def d(s):
    return date(int(s[:4]), int(s[5:7]), int(s[8:10])) if s else None


def flag(r, col):
    return r.get(col, "").strip().lower() in ("true", "1")


def norm(name):
    return name.replace(" ", "")


# 행정동: 공용 파일(좌표로 배정) → 비어 있으면 주소로 찾은 값
fill = {r["mgt_no"]: (r["gu"], r["adm_cd"], r["adm_nm"])
        for r in csv.DictReader(open(os.path.join(ROOT, "jari", "dong_fill.csv"), encoding="utf-8-sig"))}

by_site, no_close, temp, after = C.defaultdict(list), 0, 0, 0
for r in csv.DictReader(open(os.path.join(ROOT, "data", "base", "permits_base.csv"), encoding="utf-8-sig")):
    key = jibun_key(r["jibun_addr"])
    if not key or not r["permit_date"]:
        continue
    # 폐업일이 없으면 지금 영업 중으로 잘못 셈. close_date_missing 열이 없던 공용 파일도 상태로 같이 거른다
    if flag(r, "close_date_missing") or (r["status"] == "폐업" and not r["close_date"]):
        no_close += 1
        continue
    if flag(r, "is_temp"):
        temp += 1
        continue
    if r["permit_date"] > BASE.isoformat():
        after += 1
        continue
    if r["close_date"] > BASE.isoformat():   # 기준일에는 영업 중이었다
        r["close_date"] = ""
    r["_dong"] = (r["gu"], r["adm_cd"], r["adm_nm"]) if r["adm_cd"] else fill.get(r["mgt_no"], ("", "", ""))
    by_site[key].append(r)

sites, history, merged_total = [], [], 0
for key, raw in by_site.items():
    raw.sort(key=lambda r: r["permit_date"])

    # 같은 가게 합치기
    stores = []
    for r in raw:
        s = {"name": r["name"], "uptae": r["uptae"], "kind": r["source"],
             "open": d(r["permit_date"]), "close": d(r["close_date"]), "ids": [r["mgt_no"]],
             "dong": r["_dong"]}
        prev = next((p for p in reversed(stores)
                     if norm(p["name"]) == norm(s["name"]) and p["close"]
                     and MERGE_DAYS[0] <= (s["open"] - p["close"]).days <= MERGE_DAYS[1]), None)
        if prev:
            # 새 허가가 이전 폐업보다 먼저 날 수 있어, 더 늦은 폐업일을 남긴다 (둘 중 하나라도 영업 중이면 영업 중)
            prev["close"] = None if s["close"] is None or prev["close"] is None else max(prev["close"], s["close"])
            prev["ids"] += s["ids"]; merged_total += 1
            if s["dong"][1]: prev["dong"] = s["dong"]
        else:
            stores.append(s)

    recent = [s for s in stores if (s["close"] or BASE) >= CUT]
    if not recent:
        continue

    # 최대 동시 영업 수 (최근 10년 안에 영업한 가게 기준)
    events = sorted([(max(s["open"], CUT), 1) for s in recent] + [((s["close"] or BASE), -1) for s in recent],
                    key=lambda e: (e[0], e[1]))
    cur = peak = 0
    for _, step in events:
        cur += step; peak = max(peak, cur)
    peak = max(peak, 1)  # 10년 시작일에 바로 폐업한 가게만 있는 경우

    opened_10y = [s for s in stores if s["open"] >= CUT]
    closed_10y = [s for s in recent if s["close"]]
    months = [round((s["close"] - s["open"]).days / 30.44) for s in closed_10y]
    now = [s for s in stores if not s["close"]]
    dongs = C.Counter(s["dong"] for s in recent if s["dong"][1])
    gu, adm_cd, dong = dongs.most_common(1)[0][0] if dongs else (key.split()[0], "", "")

    sites.append({
        "site_key": key, "gu": gu, "adm_cd": adm_cd, "hemd_name": dong,
        "permits_10y": len(opened_10y),
        "max_concurrent": peak,
        "per_slot_10y": round(len(opened_10y) / peak, 2),
        "closed_10y": len(closed_10y),
        "avg_months_closed": round(S.mean(months), 1) if months else "",
        "open_now": len(now),
        "open_now_names": " / ".join(s["name"] for s in now),
    })
    for s in stores:
        history.append({
            "site_key": key, "mgtno": " ".join(s["ids"]), "name": s["name"], "kind": s["kind"],
            "uptae": s["uptae"], "opened": s["open"].isoformat(),
            "closed": s["close"].isoformat() if s["close"] else "",
            "months": round(((s["close"] or BASE) - s["open"]).days / 30.44),
            "merged": len(s["ids"]) - 1,
        })

# 동네 기준값: 같은 행정동 단독 자리들의 평균 인허가 건수, 전체 자리의 한 칸당 평균
single = C.defaultdict(list); slot = C.defaultdict(list)
for s in sites:
    if not s["hemd_name"]:
        continue
    k = (s["gu"], s["hemd_name"])
    slot[k].append(s["per_slot_10y"])
    if s["max_concurrent"] == 1:
        single[k].append(s["permits_10y"])
for s in sites:
    k = (s["gu"], s["hemd_name"])
    s["dong_avg_single"] = round(S.mean(single[k]), 2) if single.get(k) else ""
    s["dong_avg_per_slot"] = round(S.mean(slot[k]), 2) if slot.get(k) else ""

if not sites:
    raise SystemExit("최근 10년 영업한 자리가 없습니다. permits_base.csv를 확인하세요")
for name, rows in [("sites.csv", sites), ("site_history.csv", history)]:
    with open(os.path.join(DATA, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

# 요약
n = len(sites)
singles = [s for s in sites if s["max_concurrent"] == 1]
print(f"기준일 {BASE}, 최근 10년 영업한 자리: {n:,}곳")
print(f"  같은 가게로 합친 재인허가 {merged_total:,}건, 뺀 업소: 폐업일 없음 {no_close:,} / 팝업 {temp:,} / 기준일 뒤 인허가 {after:,}")
print(f"행정동 붙은 자리: {sum(1 for s in sites if s['hemd_name']) / n:.1%}")
print(f"단독 점포 자리: {len(singles):,}곳 ({len(singles) / n:.0%}), 여러 점포 건물: {n - len(singles):,}곳")
print("단독 자리 10년 인허가 건수 분포:", sorted(C.Counter(min(s["permits_10y"], 6) for s in singles).items()), "(6 = 6건 이상)")
if singles:
    print(f"단독 자리 평균 {S.mean(s['permits_10y'] for s in singles):.2f}건, 4건 이상 {sum(1 for s in singles if s['permits_10y'] >= 4):,}곳")
closed_months = [h["months"] for h in history if h["closed"] and h["closed"] >= CUT.isoformat()]
if closed_months:
    print(f"폐업 가게 평균 영업 기간: {S.mean(closed_months):.1f}개월")
dong_avgs = sorted(((k, S.mean(v), len(v)) for k, v in single.items() if len(v) >= 30), key=lambda x: x[1])
print("단독 자리 30곳 이상 행정동 중 평균 교체가 많은 곳:", [(f"{k[0]} {k[1]}", round(a, 2)) for k, a, _ in dong_avgs[-5:][::-1]])
print("적은 곳:", [(f"{k[0]} {k[1]}", round(a, 2)) for k, a, _ in dong_avgs[:5]])
