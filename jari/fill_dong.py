"""공용 파일(permits_base.csv)에서 행정동이 빈 업소를 주소 조회 결과로 채운다.

입력: data/base/permits_base.csv (경쟁 축 공용 파일), data/seoul/permit_hemd.csv (hemd.py),
      competition/dong_area.csv (행정동 기준표)
출력: jari/dong_fill.csv — 행정동이 빈 업소 중 주소로 찾은 것 (source, mgt_no, adm_cd, adm_nm, gu, via, is_open)

주소 API 행정동 이름은 기준표와 표기가 달라 맞춰 준다: 망원제1동 → 망원1동, 종로1.2.3.4가동 → 종로1·2·3·4가동
좌표로 행정동이 이미 있는 업소는 두 방식이 같은 동을 붙였는지 비교만 한다 (교차 검증).
공용 파일에 dong_via 열이 있으면(이 표로 이미 채운 공용 파일) 좌표로 붙인 것(coord)만 "이미 있음"으로 본다.
그래서 채워진 공용 파일로 다시 돌려도 같은 결과가 나온다.
행정동 경계에 걸친 지번(주소 API가 "광희동,신당동"처럼 여러 동을 줌)은 첫 번째 동 대신
같은 지번의 다른 업소들이 좌표로 받은 행정동 중 가장 많은 것을 쓴다. 좌표 있는 업소가 없으면 채우지 않는다.
"""
import csv, json, os, re, collections as C
from common import ROOT, DATA, exact_hits, jibun_key

BASE = os.path.join(ROOT, "data", "base", "permits_base.csv")
HEMD = os.path.join(DATA, "permit_hemd.csv")
DONG = os.path.join(ROOT, "competition", "dong_area.csv")
OUT = os.path.join(ROOT, "jari", "dong_fill.csv")  # 경쟁 축이 받아 쓰도록 저장소에 올림


def by_coord(r):
    """좌표로 붙인 행정동이 있는가. dong_via 가 없는 예전 공용 파일은 adm_cd 가 곧 좌표 기준"""
    return bool(r["adm_cd"]) and r.get("dong_via", "coord") in ("coord", None)


def norm(name):
    return re.sub(r"제(\d)", r"\1", name, count=1).replace(".", "·")


code = {(r["gu"], r["adm_nm"]): r["adm_cd"] for r in csv.DictReader(open(DONG, encoding="utf-8-sig"))}

juso = {}
for r in csv.DictReader(open(HEMD, encoding="utf-8")):
    if r["hemd_name"]:
        juso[r["mgtno"]] = (r["gu"], r["hemd_name"], r["via"], r["jibun_key"])

# 경계 지번과, 그 지번에서 좌표로 행정동을 받은 업소들의 다수 행정동
raw = json.load(open(os.path.join(DATA, "juso_jibun.json")))
boundary = {k for k, v in raw.items() if any("," in (h.get("hemd") or "") for h in exact_hits(k, v))}
lot_dong = C.defaultdict(C.Counter)
for r in csv.DictReader(open(BASE, encoding="utf-8-sig")):
    k = jibun_key(r["jibun_addr"])
    if by_coord(r) and k in boundary:
        lot_dong[k][(r["gu"], r["adm_nm"], r["adm_cd"])] += 1

fill, check, unknown, edge = [], C.Counter(), C.Counter(), C.Counter()
for r in csv.DictReader(open(BASE, encoding="utf-8-sig")):
    hit = juso.get(r["mgt_no"])
    if not hit:
        continue
    gu, nm, via, key = hit
    if not by_coord(r) and via == "jibun" and key in boundary:
        if not lot_dong[key]:
            edge["좌표 있는 업소 없어 비움"] += 1
            continue
        (gu, nm, cd), _ = lot_dong[key].most_common(1)[0]
        edge["같은 지번 좌표 기준으로 정함"] += 1
        fill.append({"source": r["source"], "mgt_no": r["mgt_no"], "adm_cd": cd, "adm_nm": nm, "gu": gu,
                     "via": via, "is_open": r["is_open"]})
        continue
    if (gu, nm) not in code:          # 기준표에도 '상일제1동'처럼 '제'가 남은 이름이 있어 그대로 먼저 찾는다
        nm = norm(nm)
    cd = code.get((gu, nm))
    if not cd:
        unknown[(gu, nm)] += 1
        continue
    if by_coord(r):
        check["같음" if r["adm_cd"] == cd else "다름"] += 1
    else:
        fill.append({"source": r["source"], "mgt_no": r["mgt_no"], "adm_cd": cd, "adm_nm": nm, "gu": gu,
                     "via": via, "is_open": r["is_open"]})

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["source", "mgt_no", "adm_cd", "adm_nm", "gu", "via", "is_open"])
    w.writeheader(); w.writerows(fill)

print(f"행정동 채움: {len(fill):,}건 (영업 중 {sum(1 for x in fill if x['is_open'] == 'True'):,}건) → {OUT}")
if not fill:
    print("  채운 업소가 없습니다. 공용 파일과 permit_hemd.csv 를 확인하세요")
total = sum(check.values())
if total:
    print(f"교차 검증 (좌표·주소 둘 다 있는 업소 {total:,}곳): 같은 동 {check['같음'] / total:.2%}, 다른 동 {check['다름']:,}곳")
print("행정동 경계 지번:", dict(edge))
print("기준표에 없는 이름:", dict(unknown))
