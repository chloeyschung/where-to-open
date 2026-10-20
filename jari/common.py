"""collect.py · hemd.py · fill_dong.py · sites.py가 같이 쓰는 설정, API 호출, 지번 키 규칙."""
import json, os, re, time, urllib.parse, urllib.request
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data", "seoul")
# 팀 공통 기준일 (docs/common-rules.md 규칙 2). 이 날 뒤의 인허가·폐업은 쓰지 않는다
# 월 배치(batch/run.py)는 환경변수 WTO_BASE_DATE 로 지난달 말일을 넘겨준다. 없으면 2026-09-30
BASE = date.fromisoformat(os.environ.get("WTO_BASE_DATE", "2026-09-30"))
CUT = date(BASE.year - 10, BASE.month, min(BASE.day, 28 if BASE.month == 2 else BASE.day))  # 최근 10년 시작


def env():
    return dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l)


# 지번 키(구 동 번지): "서울특별시 마포구 망원동 329-1 2층" → "마포구 망원동 329-1"
# 수집할 때와 자리를 묶을 때 같은 키를 써야 하므로 여기 한 곳에만 둔다
JIBUN_PAT = re.compile(r"^서울특별시 (\S+구) (\S+) (산\s*)?(\d+(?:-\d+)?)(?:\s|,|\(|$)")


def jibun_key(addr):
    m = JIBUN_PAT.match(addr or "")
    if not m:
        return None
    # 번지를 숫자로 맞춘다: "106-0" → "106" (부번 0은 본번과 같은 지번), "256-0257" → "256-257"
    # 본번 0("0-0", "000")은 번지를 모른다는 뜻이라 자리로 묶지 않는다
    main, _, sub = m.group(4).partition("-")
    main, sub = int(main), int(sub or 0)
    if main == 0:
        return None
    return f"{m.group(1)} {m.group(2)} {'산' if m.group(3) else ''}{main}{f'-{sub}' if sub else ''}"


def exact_hits(key, res):
    """주소 검색은 앞부분 일치라 329를 찾으면 329-1도 나온다. 지번이 정확히 같은 결과만 남긴다."""
    return [h for h in res.get("hits", []) if re.match(r"^서울특별시 " + re.escape(key) + r"(\s|$)", h["jibun"])]


def get(url, ok=lambda d: True, tries=5):
    """JSON을 받는다. 네트워크 오류이거나 ok(d)가 거짓이면 다시 시도한다.
    끝내 ok가 안 되면 마지막으로 받은 응답(오류 응답)을, 한 번도 못 받았으면 None을 돌려준다."""
    last = None
    for i in range(tries):
        try:
            last = json.load(urllib.request.urlopen(url, timeout=60))
            if ok(last):
                return last
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    return last


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
        if d is None or "results" not in d:
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
