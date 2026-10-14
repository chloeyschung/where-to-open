"""collect.py · hemd.py · sites.py가 같이 쓰는 설정, API 호출, 지번 키 규칙."""
import json, os, re, time, urllib.parse, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data", "seoul")


def env():
    return dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l)


# 지번 키(구 동 번지): "서울특별시 마포구 망원동 329-1 2층" → "마포구 망원동 329-1"
# 수집할 때와 자리를 묶을 때 같은 키를 써야 하므로 여기 한 곳에만 둔다
JIBUN_PAT = re.compile(r"^서울특별시 (\S+구) (\S+) (산\s*)?(\d+(?:-\d+)?)(?:\s|,|\(|$)")


def jibun_key(addr):
    m = JIBUN_PAT.match(addr or "")
    return f"{m.group(1)} {m.group(2)} {'산' if m.group(3) else ''}{m.group(4)}" if m else None


def get(url, ok=lambda d: True, tries=5):
    """JSON을 받는다. 네트워크 오류이거나 ok(d)가 거짓이면 다시 시도하고, 끝내 실패하면 None."""
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(url, timeout=60))
            if ok(d):
                return d
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    return None


JUSO_PAGE = 100  # 검색API 한 페이지 최대 건수
JUSO_PAGES = 10  # 앞부분 일치 검색이라 결과가 많을 수 있어 최대 1,000건까지 받는다


def juso(kw, key):
    """도로명주소 검색API. {"hits": [...], "total": n} 또는 {"err": "..."}.
    네트워크 실패는 err "network"로 돌려줘 '결과 없음'과 구분한다."""
    hits, total = [], None
    for page in range(1, JUSO_PAGES + 1):
        u = "https://business.juso.go.kr/addrlink/addrLinkApi.do?" + urllib.parse.urlencode(
            {"confmKey": key, "currentPage": page, "countPerPage": JUSO_PAGE, "keyword": kw,
             "resultType": "json", "addInfoYn": "Y"})
        d = get(u, ok=lambda d: d["results"]["common"]["errorCode"] != "-999")  # -999 = 일시적 시스템 오류
        if d is None:
            return {"err": "network"}
        c = d["results"]["common"]
        if c["errorCode"] != "0":
            return {"err": c["errorCode"] + " " + c["errorMessage"]}
        total = int(c["totalCount"])
        hits += [{"bd": j["bdMgtSn"], "hemd": j.get("hemdNm"), "adm": j["admCd"],
                  "jibun": j["jibunAddr"], "road": j["roadAddrPart1"]} for j in d["results"]["juso"] or []]
        if len(hits) >= total:
            break
    return {"hits": hits, "total": total}
