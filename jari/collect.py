"""서울시 인허가 데이터를 받고 지번마다 행정동을 조회한다.

1. 서울시 Open API로 일반음식점·휴게음식점·제과점 전체 수집 (폐업 포함)
2. 관리번호 중복 제거, 지번 키(구 동 번지) 생성 → dedup.json
3. 도로명주소 검색API로 지번마다 조회 → juso_jibun.json (2천 건마다 저장, 다시 실행하면 이어서 하고 오류 난 지번은 다시 조회)

결과는 data/seoul/ 에 저장된다. 인증키는 저장소 루트 .env 의 SEOUL_API_KEY, JUSO_API_KEY.
"""
import json, os, time, concurrent.futures as F
from common import DATA, env, get, juso, jibun_key

ENV = env()
os.makedirs(DATA, exist_ok=True)
os.chdir(DATA)
SK = ENV["SEOUL_API_KEY"]
JK = ENV["JUSO_API_KEY"]
def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

# 1) 서울 전체 인허가
for s in ["LOCALDATA_072404", "LOCALDATA_072405", "LOCALDATA_072218"]:
    if os.path.exists(f"{s}.json"): continue
    u = lambda a, b: f"http://openapi.seoul.go.kr:8088/{SK}/json/{s}/{a}/{b}/"
    # 오류여도 HTTP 200으로 {"RESULT": {"CODE": "ERROR-..."}}가 오므로 본문에 데이터가 있는지 보고 다시 시도
    page = lambda a, b: (get(u(a, b), ok=lambda d: s in d) or {}).get(s)
    first = page(1, 1)
    if first is None:
        raise SystemExit(f"{s}: 서울 API 응답 없음. 인증키와 서비스명을 확인하세요")
    n = first["list_total_count"]
    starts = list(range(1, n + 1, 1000))
    with F.ThreadPoolExecutor(4) as ex:
        parts = list(ex.map(lambda a: page(a, min(a + 999, n)), starts))
    if None in parts:
        raise SystemExit(f"{s}: {parts.count(None)}개 페이지를 받지 못함. 다시 실행하세요")
    rows = [r for p in parts for r in p["row"]]
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
for r in rows:
    r["_k"] = jibun_key(r["SITEWHLADDR"])
json.dump(rows, open("dedup.json", "w"), ensure_ascii=False)
keys = sorted({r["_k"] for r in rows if r["_k"]})
log("업소", len(rows), "지번키 실패", sum(1 for r in rows if not r["_k"]), "고유 지번", len(keys))

# 3) 지번 → 행정동 (체크포인트 저장)
done = json.load(open("juso_jibun.json")) if os.path.exists("juso_jibun.json") else {}
# 다시 조회: 처음 보는 지번, 오류 난 지번, 예전 방식(첫 50건만 받음)으로 50건이 꽉 찬 지번
todo = [k for k in keys if k not in done or "err" in done[k]
        or ("total" not in done[k] and len(done[k]["hits"]) == 50)]
log("지번 조회 남은 수", len(todo))
with F.ThreadPoolExecutor(8) as ex:
    for i, (k, v) in enumerate(zip(todo, ex.map(lambda k: juso("서울특별시 " + k, JK), todo)), 1):
        done[k] = v
        if "err" in v: log("API 오류", k, v["err"])
        if i % 2000 == 0:
            json.dump(done, open("juso_jibun.json", "w"), ensure_ascii=False); log("지번", i, "/", len(todo))
json.dump(done, open("juso_jibun.json", "w"), ensure_ascii=False)
log("지번 조회 완료", len(done), "오류", sum(1 for v in done.values() if "err" in v),
    "결과가 잘린 지번", sum(1 for v in done.values() if "total" in v and len(v["hits"]) < v["total"]))
