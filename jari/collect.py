"""서울시 인허가 데이터를 받고 지번마다 행정동을 조회한다.

1. 서울시 Open API로 일반음식점·휴게음식점·제과점 전체 수집 (폐업 포함)
2. 관리번호 중복 제거, 지번 키(구 동 번지) 생성 → dedup.json
3. 도로명주소 검색API로 지번마다 조회 → juso_jibun.json (2천 건마다 저장, 다시 실행하면 이어서 함)

결과는 data/seoul/ 에 저장된다. 인증키는 저장소 루트 .env 의 SEOUL_API_KEY, JUSO_API_KEY.
"""
import json, re, os, time, urllib.request, urllib.parse, concurrent.futures as F
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENV = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l)
DATA = os.path.join(ROOT, "data", "seoul")
os.makedirs(DATA, exist_ok=True)
os.chdir(DATA)
SK = ENV["SEOUL_API_KEY"]
JK = ENV["JUSO_API_KEY"]
def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def get(url, tries=5):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(url, timeout=60))
        except Exception: time.sleep(3 * (i + 1))
    raise RuntimeError(url)

# 1) 서울 전체 인허가
for s in ["LOCALDATA_072404", "LOCALDATA_072405", "LOCALDATA_072218"]:
    if os.path.exists(f"{s}.json"): continue
    u = lambda a, b: f"http://openapi.seoul.go.kr:8088/{SK}/json/{s}/{a}/{b}/"
    n = get(u(1, 1))[s]["list_total_count"]
    starts = list(range(1, n + 1, 1000))
    with F.ThreadPoolExecutor(4) as ex:
        parts = list(ex.map(lambda a: get(u(a, min(a + 999, n)))[s]["row"], starts))
    rows = [r for p in parts for r in p]
    json.dump(rows, open(f"{s}.json", "w"), ensure_ascii=False)
    log(s, n, len(rows))

# 2) 중복 제거 + 지번 키
rows = []
for s, t in [("LOCALDATA_072404", "일반"), ("LOCALDATA_072405", "휴게"), ("LOCALDATA_072218", "제과")]:
    for r in json.load(open(f"{s}.json")):
        r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}; r["_t"] = t; rows.append(r)
uniq = {}
for r in rows: uniq[(r["OPNSFTEAMCODE"], r["MGTNO"])] = r
rows = list(uniq.values())
pat = re.compile(r"^서울특별시 (\S+구) (\S+) (산\s*)?(\d+(?:-\d+)?)(?:\s|,|\(|$)")
for r in rows:
    m = pat.match(r["SITEWHLADDR"])
    r["_k"] = f"{m.group(1)} {m.group(2)} {'산' if m.group(3) else ''}{m.group(4)}" if m else None
json.dump(rows, open("dedup.json", "w"), ensure_ascii=False)
keys = sorted({r["_k"] for r in rows if r["_k"]})
log("업소", len(rows), "지번키 실패", sum(1 for r in rows if not r["_k"]), "고유 지번", len(keys))

# 3) 지번 → 행정동 (체크포인트 저장)
def juso(kw):
    u = "https://business.juso.go.kr/addrlink/addrLinkApi.do?" + urllib.parse.urlencode(
        {"confmKey": JK, "countPerPage": 50, "keyword": kw, "resultType": "json", "addInfoYn": "Y"})
    try: d = get(u)["results"]
    except RuntimeError: return {"err": "network"}
    if d["common"]["errorCode"] != "0": return {"err": d["common"]["errorCode"] + " " + d["common"]["errorMessage"]}
    return {"hits": [{"bd": j["bdMgtSn"], "hemd": j.get("hemdNm"), "adm": j["admCd"], "jibun": j["jibunAddr"], "road": j["roadAddrPart1"]} for j in d["juso"]]}
done = json.load(open("juso_jibun.json")) if os.path.exists("juso_jibun.json") else {}
todo = [k for k in keys if k not in done or done[k].get("err") == "network"]
log("지번 조회 남은 수", len(todo))
with F.ThreadPoolExecutor(8) as ex:
    for i, (k, v) in enumerate(zip(todo, ex.map(lambda k: juso("서울특별시 " + k), todo)), 1):
        done[k] = v
        if "err" in v and v["err"].startswith("E"): log("API 오류", k, v["err"])
        if i % 2000 == 0:
            json.dump(done, open("juso_jibun.json", "w"), ensure_ascii=False); log("지번", i, "/", len(todo))
json.dump(done, open("juso_jibun.json", "w"), ensure_ascii=False)
log("지번 조회 완료", len(done))
