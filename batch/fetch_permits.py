"""서울 열린데이터광장 Open API로 인허가 3종 전체를 받아 permits_prep.py 입력 CSV로 저장한다.

  LOCALDATA_072404 일반음식점 → restaurant.csv
  LOCALDATA_072405 휴게음식점 → cafe.csv
  LOCALDATA_072218 제과점영업 → bakery.csv

- 값 앞뒤 공백을 지운다 (API는 "  영업/정상  "처럼 공백을 붙여 준다)
- 같은 관리번호가 여러 번 오면 가장 최근에 수정된 행만 남긴다 (jari/collect.py 와 같은 규칙)
- 컬럼 이름은 API 영문 그대로 둔다. permits_prep.py 의 COLUMN_MAP 이 API 이름을 읽는다

  python batch/fetch_permits.py --out data/raw                 # API에서 받기 (SEOUL_API_KEY 필요)
  python batch/fetch_permits.py --out data/raw --from-json data/seoul   # 이미 받은 JSON으로 만들기 (테스트용)
"""
import argparse
import concurrent.futures as F
import csv
import json
import os
import time
from pathlib import Path

import requests

SERVICES = {"LOCALDATA_072404": "restaurant", "LOCALDATA_072405": "cafe", "LOCALDATA_072218": "bakery"}
PAGE = 1000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def fetch(service, key, session):
    def page(a, b, tries=5):
        url = f"http://openapi.seoul.go.kr:8088/{key}/json/{service}/{a}/{b}/"
        for i in range(tries):
            try:
                d = session.get(url, timeout=60).json()
                if service in d:  # 오류여도 HTTP 200으로 {"RESULT": ...}가 온다
                    return d[service]
            except (requests.RequestException, ValueError):
                pass
            time.sleep(2 * (i + 1))
        return None

    first = page(1, 1)
    if first is None:
        raise SystemExit(f"{service}: 서울 API 응답 없음. 인증키와 서비스 이름을 확인하세요")
    n = int(first["list_total_count"])
    starts = list(range(1, n + 1, PAGE))
    with F.ThreadPoolExecutor(4) as ex:
        parts = list(ex.map(lambda a: page(a, min(a + PAGE - 1, n)), starts))
    missing = sum(p is None for p in parts)
    if missing:
        raise SystemExit(f"{service}: {missing}개 페이지를 받지 못했습니다")
    rows = [r for p in parts for r in p["row"]]
    if len(rows) != n:
        raise SystemExit(f"{service}: 건수가 다릅니다 (API {n:,}, 받은 행 {len(rows):,})")
    return rows


def clean(rows):
    uniq = {}
    for r in rows:
        r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
        k = (r.get("OPNSFTEAMCODE"), r["MGTNO"])
        if k not in uniq or (r.get("UPDATEDT") or "") >= (uniq[k].get("UPDATEDT") or ""):
            uniq[k] = r
    return list(uniq.values())


def write_csv(rows, path):
    cols = list(rows[0].keys())
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)  # 끝까지 쓴 파일만 남긴다


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="CSV를 쓸 폴더")
    ap.add_argument("--from-json", help="API 대신 이 폴더의 LOCALDATA_*.json 을 읽음")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    key = os.environ.get("SEOUL_API_KEY", "")
    if not a.from_json and not key:
        raise SystemExit("SEOUL_API_KEY 환경변수가 필요합니다")
    for service, name in SERVICES.items():
        if a.from_json:
            rows = json.load(open(Path(a.from_json) / f"{service}.json", encoding="utf-8"))
        else:
            rows = fetch(service, key, session)
        rows = clean(rows)
        write_csv(rows, out / f"{name}.csv")
        log(f"{service} → {name}.csv {len(rows):,}건")


if __name__ == "__main__":
    main()
