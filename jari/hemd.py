"""collect.py 결과를 정리해 업소마다 행정동을 붙인다 → data/seoul/permit_hemd.csv

1. 검색 결과 중 지번이 정확히 같은 것만 남긴다 (검색은 앞부분 일치라 329 → 329-1도 나옴)
2. 못 찾은 지번은 도로명주소로 다시 조회한다 (재개발·합필로 지번이 바뀐 경우)
3. 지번별 행정동 표(csv)와 커버리지 숫자를 남긴다
"""
import csv, json, os, re, collections as C, concurrent.futures as F
from common import DATA as HERE, CUT, env, exact_hits, juso

JK = env()["JUSO_API_KEY"]


def dong_of(hit):
    # "서울특별시 마포구 망원제1동" → "마포구 망원제1동" (같은 이름이 여러 구에 있어 구까지 붙임)
    # 경계에 걸치면 "서강동,합정동" → 첫 번째 (공용 파일 행정동을 채울 때는 fill_dong.py가 같은 지번 좌표 기준으로 다시 정함)
    if not hit.get("hemd"): return None
    p = hit["hemd"].split()
    return f"{p[1]} {p[-1].split(',')[0]}" if len(p) >= 3 else None


rows = json.load(open(os.path.join(HERE, "dedup.json")))
raw = json.load(open(os.path.join(HERE, "juso_jibun.json")))

# 1) 정확 일치
by_key, amb = {}, 0
for k, v in raw.items():
    hits = exact_hits(k, v)
    dongs = {dong_of(h) for h in hits if dong_of(h)}
    if hits and len(dongs) == 1:
        by_key[k] = dongs.pop()
    elif len(dongs) > 1:
        amb += 1

# 2) 도로명 재조회: 지번으로 못 찾은 업소의 도로명주소
road_pat = re.compile(r"^서울특별시 (\S+구) (\S+(?:로|길)\S*\s+\d+(?:-\d+)?)")
need = {}
for r in rows:
    if r["_k"] in by_key:
        continue
    m = road_pat.match(r["RDNWHLADDR"])
    if m:
        need.setdefault(f"{m.group(1)} {m.group(2)}", []).append(r)


def road_lookup(addr):
    res = juso("서울특별시 " + addr, JK)
    if "err" in res:
        return addr, res
    hits = [h for h in res["hits"] if h["road"] == "서울특별시 " + addr]
    return addr, ({"hemd": dong_of(hits[0])} if hits else None)


with F.ThreadPoolExecutor(8) as ex:
    road = dict(ex.map(road_lookup, sorted(need)))
failed = {a: v["err"] for a, v in road.items() if v and "err" in v}
if failed:
    # 조회 실패를 '주소 없음'으로 넘기면 행정동이 조용히 빠지므로 멈춘다
    raise SystemExit(f"도로명 조회 {len(failed):,}건 실패 (예: {next(iter(failed.items()))}). 잠시 뒤 다시 실행하세요")

# 업소별 행정동 확정
def assign(r):
    if r["_k"] in by_key:
        return by_key[r["_k"]], "jibun"
    m = road_pat.match(r["RDNWHLADDR"])
    hit = road.get(f"{m.group(1)} {m.group(2)}") if m else None
    if hit and hit["hemd"]:
        return hit["hemd"], "road"
    return None, "coord" if r["X"] else "none"


out = []
for r in rows:
    hemd, via = assign(r)
    out.append({"opnsfteamcode": r["OPNSFTEAMCODE"], "mgtno": r["MGTNO"], "jibun_key": r["_k"] or "",
                "gu": hemd.split()[0] if hemd else "", "hemd_name": hemd.split()[1] if hemd else "", "via": via})

with open(os.path.join(HERE, "permit_hemd.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader(); w.writerows(out)

# 3) 숫자
def cover(sub, label):
    c = C.Counter(o["via"] for o in sub)
    n = len(sub)
    print(f"{label}: {n:,}곳 | 지번 {c['jibun'] / n:.1%} | 도로명 {c['road'] / n:.1%} | 좌표로 채울 것 {c['coord'] / n:.1%} | 둘 다 없음 {c['none'] / n:.1%}")

# sites.py와 같은 대상: 폐업했는데 폐업일이 빈 업소는 뺀다
recent = {(r["OPNSFTEAMCODE"], r["MGTNO"]) for r in rows
          if r["DCBYMD"] >= CUT.isoformat() or (not r["DCBYMD"] and r["TRDSTATENM"] != "폐업")}
cover(out, "전체 업소")
cover([o for o in out if (o["opnsfteamcode"], o["mgtno"]) in recent], "최근 10년 업소")
print("한 지번에 행정동이 둘 이상 나와 보류한 지번:", amb)
print("행정동 수:", len({(o['gu'], o['hemd_name']) for o in out if o['hemd_name']}), " 구 수:", len({o['gu'] for o in out if o['gu']}))
cross = sum(1 for r, o in zip(rows, out) if o["gu"] and r["_k"] and not r["_k"].startswith(o["gu"] + " "))
print("주소의 구와 행정동의 구가 다른 업소(구 경계):", cross)
print("구별 최근 10년 커버리지 하위 5:")
g = C.defaultdict(C.Counter)
for o in out:
    if (o["opnsfteamcode"], o["mgtno"]) in recent and o["gu"]:
        g[o["gu"]][bool(o["hemd_name"])] += 1
for gu, c in sorted(g.items(), key=lambda x: x[1][True] / sum(x[1].values()))[:5]:
    print(f"   {gu}: {c[True] / sum(c.values()):.1%}")
