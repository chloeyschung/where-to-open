"""
서울시 인허가 데이터 수집 (일반음식점 + 휴게음식점)

출처: 서울열린데이터광장 OpenAPI (제공: 서울특별시 시민건강국 식품정책과, 공공누리 1유형)
  - 서울시 일반음식점 인허가 정보  서비스명 LOCALDATA_072404
  - 서울시 휴게음식점 인허가 정보  서비스명 LOCALDATA_072405
  원본시스템: 공공데이터포털(지방행정 인허가정보)

이 API는 변동분이 아니라 '전체' 데이터를 1회 최대 1,000건씩 페이지로 내려준다.
폐업 업소도 포함되어 있어 생존율·교체율 계산에 그대로 쓸 수 있다.

인증키 설정 (저장소에 커밋하지 않는다):
  cp .env.example .env   후  .env 의 SEOUL_API_KEY= 뒤에 발급받은 키 입력
  (.env 는 .gitignore 에 들어 있음. Render 에서는 대시보드 Environment 에 같은 이름으로 등록)

사용법:
  python collect.py --check               # 인증키·접속만 확인 (서비스당 1건)
  python collect.py                       # 전체 수집 (.env 의 키 사용)
  python collect.py --key sample          # 키 없이 동작 확인 (서비스당 5건)

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
    # 로그·에러 메시지에 인증키가 찍히지 않도록 가린다
    raise RuntimeError(f"{url.replace(key, mask(key))} 요청 실패: {last_err}")


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


ENV_NAME = "SEOUL_API_KEY"


def mask(key):
    return key if key == "sample" or len(key) < 8 else key[:4] + "*" * (len(key) - 8) + key[-4:]


def load_dotenv():
    """python-dotenv 없이 .env 읽기. stability/.env → 저장소 루트 .env 순서로 찾는다.
    이미 설정된 환경변수(예: Render 대시보드에서 넣은 값)는 덮어쓰지 않는다."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"), os.path.join(os.path.dirname(here), ".env")):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return path
    return None


def resolve_key(cli_key):
    """우선순위: --key > 환경변수 SEOUL_API_KEY > .env 파일"""
    if cli_key:
        return cli_key, "--key 인자"
    if os.environ.get(ENV_NAME):
        return os.environ[ENV_NAME], "환경변수"
    src = load_dotenv()
    if os.environ.get(ENV_NAME):
        return os.environ[ENV_NAME], src
    sys.exit(f"인증키가 없습니다. stability/.env 파일에 {ENV_NAME}=발급받은키 를 넣거나 "
             f"--key 로 넘겨주세요. (.env.example 참고)")


def check(key):
    """서비스별로 1건만 요청해 인증키·접속을 확인"""
    ok = True
    for svc, name in SERVICES.items():
        try:
            body = fetch(key, svc, 1, 1, retries=2)
            print(f"  OK  {svc} {name}: 전체 {int(body.get('list_total_count', 0)):,}건")
        except RuntimeError as e:
            ok = False
            print(f"  실패 {svc} {name}: {e}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help=f"인증키 (생략하면 환경변수/.env 의 {ENV_NAME} 사용, 테스트는 sample)")
    ap.add_argument("--check", action="store_true", help="수집 없이 인증키·접속만 확인")
    ap.add_argument("--out", default="raw")
    ap.add_argument("--sleep", type=float, default=0.1, help="요청 간 대기(초)")
    ap.add_argument("--only", choices=list(SERVICES), help="한 서비스만 받기")
    a = ap.parse_args()
    key, src = resolve_key(a.key)
    print(f"인증키 {mask(key)} ({src})")
    if a.check:
        return check(key)
    os.makedirs(a.out, exist_ok=True)
    for svc in ([a.only] if a.only else SERVICES):
        collect(key, svc, a.out, a.sleep)


if __name__ == "__main__":
    sys.exit(main())
