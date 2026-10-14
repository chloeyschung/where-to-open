"""collect.py 결과를 정리해 업소마다 행정동을 붙인다 → data/seoul/permit_hemd.csv

1. 검색 결과 중 지번이 정확히 같은 것만 남긴다 (검색은 앞부분 일치라 329 → 329-1도 나옴)
2. 못 찾은 지번은 도로명주소로 다시 조회한다 (재개발·합필로 지번이 바뀐 경우)
3. 지번별 행정동 표(csv)와 커버리지 숫자를 남긴다
"""
import csv, json, os, re, time, urllib.parse, urllib.request, collections as C, concurrent.futures as F

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENV = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l)
HERE = os.path.join(ROOT, "data", "seoul")
JK = ENV["JUSO_API_KEY"]
CUT = "2016-10-12"  # 최근 10년


def get(url, tries=5):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def juso(kw):
    u = "https://business.juso.go.kr/addrlink/addrLinkApi.do?" + urllib.parse.urlencode(
        {"confmKey": JK, "countPerPage": 20, "keyword": kw, "resultType": "json", "addInfoYn": "Y"})
    d = get(u)
    return d["results"]["juso"] if d and d["results"]["common"]["errorCode"] == "0" else []


def dong_of(hit):
    # "서울특별시 마포구 망원제1동" → "마포구 망원제1동" (같은 이름이 여러 구에 있어 구까지 붙임)
    # 경계에 걸치면 "서강동,합정동" → 첫 번째
    if not hit.get("hemd"): return None
    p = hit["hemd"].split()
    return f"{p[1]} {p[-1].split(',')[0]}" if len(p) >= 3 else None


rows = json.load(open(os.path.join(HERE, "dedup.json")))
raw = json.load(open(os.path.join(HERE, "juso_jibun.json")))

# 1) 정확 일치
by_key = {}
for k, v in raw.items():
    hits = [h for h in v.get("hits", []) if re.match(r"^서울특별시 " + re.escape(k) + r"(\s|$)", h["jibun"])]
    dongs = {dong_of(h) for h in hits if dong_of(h)}
    if hits and len(dongs) == 1:
        by_key[k] = {"hemd": dongs.pop(), "legal_cd": hits[0]["adm"], "via": "jibun", "buildings": len({h["bd"] for h in hits})}

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
    hits = [j for j in juso("서울특별시 " + addr) if j["roadAddrPart1"] == "서울특별시 " + addr]
    return addr, ({"hemd": dong_of({"hemd": hits[0].get("hemdNm")}), "legal_cd": hits[0]["admCd"]} if hits else None)


with F.ThreadPoolExecutor(8) as ex:
    road = dict(ex.map(road_lookup, sorted(need)))

# 업소별 행정동 확정
def assign(r):
    if r["_k"] in by_key:
        return by_key[r["_k"]]["hemd"], "jibun"
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

recent = {(r["OPNSFTEAMCODE"], r["MGTNO"]) for r in rows if not r["DCBYMD"] or r["DCBYMD"] >= CUT}
cover(out, "전체 업소")
cover([o for o in out if (o["opnsfteamcode"], o["mgtno"]) in recent], "최근 10년 업소")
amb = sum(1 for k, v in raw.items() if k not in by_key and len({dong_of(h) for h in v.get("hits", []) if re.match(r"^서울특별시 " + re.escape(k) + r"(\s|$)", h["jibun"]) and dong_of(h)}) > 1)
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
