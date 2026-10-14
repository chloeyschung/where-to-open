"""
서울시 인허가 데이터 수집 (일반음식점 + 휴게음식점)

출처: 서울열린데이터광장 OpenAPI (제공: 서울특별시 시민건강국 식품정책과, 공공누리 1유형)
  - 서울시 일반음식점 인허가 정보  서비스명 LOCALDATA_072404
  - 서울시 휴게음식점 인허가 정보  서비스명 LOCALDATA_072405
  원본시스템: 공공데이터포털(지방행정 인허가정보)

이 API는 변동분이 아니라 '전체' 데이터를 1회 최대 1,000건씩 페이지로 내려준다.
폐업 업소도 포함되어 있어 생존율·교체율 계산에 그대로 쓸 수 있다.

사용법:
  python collect.py --key 발급받은_인증키
  python collect.py --key sample          # 동작 확인용 (서비스당 5건)

결과: raw/LOCALDATA_072404.csv, raw/LOCALDATA_072405.csv
중간에 끊기면 같은 명령을 다시 실행하면 받은 페이지는 건너뛰고 이어서 받는다.
표준 라이브러리만 사용한다 (설치 불필요).
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.environ.get("SEOUL_API_BASE", "http://openapi.seoul.go.kr:8088") + "/{key}/json/{svc}/{start}/{end}/"
SERVICES = {
    "LOCALDATA_072404": "일반음식점",
    "LOCALDATA_072405": "휴게음식점",
}
PAGE = 1000


def fetch(key, svc, start, end, retries=5):
    url = BASE.format(key=key, svc=svc, start=start, end=end)
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            if svc not in data:
                # 인증키 오류 등은 최상위 RESULT로 온다
                res = data.get("RESULT", data)
                raise RuntimeError(f"API 오류: {res}")
            body = data[svc]
            code = body.get("RESULT", {}).get("CODE", "")
            if code not in ("INFO-000", "INFO-200"):
                raise RuntimeError(f"API 오류: {body.get('RESULT')}")
            return body
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url} 요청 실패: {last_err}")


def collect(key, svc, outdir, sleep):
    path = os.path.join(outdir, f"{svc}.csv")
    part = path + ".part"
    state = path + ".state"

    first = fetch(key, svc, 1, 1)
    total = int(first.get("list_total_count", 0))
    if key == "sample":
        total = min(total, 5)
    print(f"[{svc} {SERVICES[svc]}] 전체 {total:,}건")

    done = 0
    if os.path.exists(state) and os.path.exists(part):
        done = int(open(state).read().strip() or 0)
        print(f"  이전 진행분 {done:,}건부터 이어받음")

    fieldnames = None
    if done and os.path.exists(part):
        with open(part, encoding="utf-8-sig") as f:
            fieldnames = next(csv.reader(f))

    mode = "a" if done else "w"
    with open(part, mode, newline="", encoding="utf-8-sig" if mode == "w" else "utf-8") as f:
        writer = None
        start = done + 1
        while start <= total:
            end = min(start + PAGE - 1, total)
            body = fetch(key, svc, start, end)
            rows = body.get("row", [])
            if writer is None:
                fieldnames = fieldnames or list(rows[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                if mode == "w":
                    writer.writeheader()
            for r in rows:
                writer.writerow({k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
            f.flush()
            with open(state, "w") as s:
                s.write(str(end))
            print(f"  {end:,}/{total:,}", end="\r", flush=True)
            start = end + 1
            time.sleep(sleep)
    os.replace(part, path)
    if os.path.exists(state):
        os.remove(state)
    print(f"\n  저장: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="서울열린데이터광장 인증키 (테스트는 sample)")
    ap.add_argument("--out", default="raw")
    ap.add_argument("--sleep", type=float, default=0.1, help="요청 간 대기(초)")
    ap.add_argument("--only", choices=list(SERVICES), help="한 서비스만 받기")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for svc in ([a.only] if a.only else SERVICES):
        collect(a.key, svc, a.out, a.sleep)


if __name__ == "__main__":
    sys.exit(main())
