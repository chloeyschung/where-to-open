"""월 배치: 공공데이터를 다시 받아 네 축을 계산하고, 검증을 통과하면 DB를 한 번에 교체한다.

GitHub Actions(.github/workflows/monthly-refresh.yml)가 매월 1일 09:00(KST)에 실행한다. 손으로도 돌릴 수 있다.

단계 (backend/app/services/freshness.py 의 STAGES 와 같은 이름)
  fetch     서울 Open API에서 인허가 3종을 받는다 (batch/fetch_permits.py)
  prepare   공용 파일·행정동 기준표·경쟁 지표를 만든다 (competition/permits_prep.py)
  axes      안정성·자리·수요 지표와 데이터 분석 페이지 숫자를 계산한다
  validate  파일·컬럼·행 수·코드·축끼리 가게 수가 맞는지 검사한다
  load      임시 표에 넣고 한 트랜잭션으로 교체한다 (backend/batch_load.py)
어느 단계든 실패하면 그 자리에서 멈추고 실패를 기록한다. load 전에 멈추면 DB는 손대지 않는다.

기준일: 지난달 말일 (한국 시간). 수요 기간: 지하철 원본이 올라온 가장 최근 달까지 25개월 (처음 적재 때와 같은 길이).
결과 파일은 저장소 폴더 안의 같은 자리에 덮어쓴다 (Actions 에서는 실행할 때만 쓰는 사본).

실행 (저장소 맨 위에서)
  python batch/run.py --no-load                       # DB 없이 계산·검증만
  python batch/run.py --trigger manual                # DATABASE_URL 이 있으면 DB까지 교체
  python batch/run.py --base-date 2026-09-30 --from-json data/seoul --no-load   # 예전에 받은 원본으로 시험
필요한 환경변수: SEOUL_API_KEY (수집), DATABASE_URL (적재)
"""
import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
KST = timezone(timedelta(hours=9))
CATS = ["카페", "제과점", "한식"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("batch")


class ValidationError(Exception):
    pass


def last_month_end(today: date) -> date:
    return today.replace(day=1) - timedelta(days=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


def demand_start(end: date) -> date:
    return add_months(end, -24)  # 끝 달을 포함해 25개월


def demand_window(base: date, probe: bool) -> tuple[date, date]:
    """수요 기간. 끝 달은 기준일이 든 달이지만, 지하철 원본(일별 CSV·시간대 API)이 아직 안 올라왔으면 한 달씩 당긴다."""
    if not probe:
        return demand_start(base), base
    import re

    import requests

    key = os.environ.get("SEOUL_API_KEY", "")
    page = requests.get("https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do", timeout=60).text
    archived = set(re.findall(r"CARD_SUBWAY_MONTH_(\d{6})\.csv", page))
    for back in range(0, 4):
        month = add_months(base, -back)
        ym = month.strftime("%Y%m")
        url = f"http://openapi.seoul.go.kr:8088/{key}/json/CardSubwayTime/1/1/{ym}"
        has_time = "CardSubwayTime" in requests.get(url, timeout=60).json()
        if ym in archived and has_time:
            end = add_months(month, 1) - timedelta(days=1)  # 그 달 말일
            if back:
                log.warning("지하철 %s 원본이 아직 없어 수요 기간 끝을 %s 로 당깁니다", base.strftime("%Y-%m"), end)
            return demand_start(end), end
    raise RuntimeError("최근 4개월 안에 지하철 일별·시간대 원본이 모두 있는 달이 없습니다")


def sh(*args, cwd=ROOT, env=None):
    log.info("$ %s", " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


# ---------------------------------------------------------------------- 단계
def step_fetch(a, env):
    raw = ROOT / "data" / "raw"
    if a.skip_fetch:
        log.info("수집 건너뜀: %s 의 CSV 사용", raw)
        return
    extra = ["--from-json", a.from_json] if a.from_json else []
    sh(PY, "batch/fetch_permits.py", "--out", raw, *extra, env=env)


def step_prepare(a, env, tmp: Path):
    raw = ROOT / "data" / "raw"
    work = tmp / "prep"
    work.mkdir()
    sh(PY, ROOT / "competition" / "permits_prep.py",
       "--cafe", raw / "cafe.csv", "--bakery", raw / "bakery.csv", "--restaurant", raw / "restaurant.csv",
       "--dong", ROOT / "demand" / "data" / "HangJeongDong_ver20260701.geojson",
       "--fill", ROOT / "jari" / "dong_fill.csv", "--asof", a.base_date.isoformat(), "--repo", ROOT,
       cwd=work, env=env)
    (ROOT / "data" / "base").mkdir(parents=True, exist_ok=True)
    shutil.copy(work / "permits_base.csv", ROOT / "data" / "base" / "permits_base.csv")
    for f in ("dong_area.csv", "competition_by_dong.csv", "uptae_counts.csv"):
        shutil.copy(work / f, ROOT / "competition" / f)


def step_axes(a, env, tmp: Path):
    sh(PY, "stability/build_stability.py", "--base", "data/base/permits_base.csv",
       "--base-date", a.base_date.isoformat(), "--extra-out", tmp / "stability_extra", env=env)
    (ROOT / "data" / "seoul").mkdir(parents=True, exist_ok=True)
    sh(PY, "sites.py", cwd=ROOT / "jari", env=env)
    sh(PY, "subway.py", "--cache", a.subway_cache or tmp / "subway", cwd=ROOT / "demand", env=env)
    sh(PY, "map_stations_to_dongs.py", cwd=ROOT / "demand", env=env)
    sh(PY, "frontend-html/analysis/build_data.py", env=env)  # 안에서 안정성·공용 파일 가게 수가 같은지 검사


def read(rel, **kw):
    path = ROOT / rel
    if not path.exists() or path.stat().st_size == 0:
        raise ValidationError(f"파일이 없거나 비었습니다: {rel}")
    return pd.read_csv(path, encoding="utf-8-sig", **kw)


def need(df, cols, name):
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValidationError(f"{name}: 컬럼이 없습니다 {sorted(missing)}")


def step_validate(a):
    dong = read("competition/dong_area.csv", dtype={"adm_cd": str})
    need(dong, ["adm_cd", "adm_nm", "gu", "area_km2"], "dong_area")
    codes = set(dong.adm_cd)
    if len(codes) != len(dong) or not all(len(c) == 10 for c in codes):
        raise ValidationError("dong_area: adm_cd 가 10자리 고유값이 아닙니다")

    comp = read("competition/competition_by_dong.csv", dtype={"adm_cd": str})
    need(comp, ["adm_cd", *CATS], "competition_by_dong")
    if set(comp.adm_cd) != codes:
        raise ValidationError("competition_by_dong: 행정동이 기준표와 다릅니다")

    st = read("stability/data/stability_by_dong.csv", dtype={"adm_cd": str})
    need(st, ["기준일", "adm_cd", "category", "영업중_현재", "표시_교체율", "교체율_기준"], "stability_by_dong")
    if set(st["기준일"]) != {a.base_date.isoformat()}:
        raise ValidationError(f"stability_by_dong: 기준일이 {a.base_date} 가 아닙니다 ({set(st['기준일'])})")
    if len(st) != len(codes) * len(CATS):
        raise ValidationError(f"stability_by_dong: {len(st)}행, 기대 {len(codes) * len(CATS)}행")
    # 두 축이 같은 가게를 셌는지: 행정동 × 업종 영업 중 가게 수가 같아야 한다 (stability/README)
    wide = st.pivot(index="adm_cd", columns="category", values="영업중_현재")
    diff = (wide[CATS].sort_index().values != comp.set_index("adm_cd")[CATS].sort_index().values).sum()
    if diff:
        raise ValidationError(f"안정성·경쟁 축의 영업 중 가게 수가 {diff}칸 다릅니다")

    dem = read("demand/subway_demand_202409_202609.csv", dtype={"adm_cd": str})
    need(dem, ["SUB_STA_NM", "adm_cd", "평일_일평균_승하차", "주말_일평균_승하차"], "subway_demand")
    if len(dem) < 250 or not set(dem.adm_cd) <= codes:
        raise ValidationError(f"subway_demand: 역 {len(dem)}곳이거나 기준표에 없는 행정동이 있습니다")

    sites = read("data/seoul/sites.csv", dtype={"adm_cd": str})
    hist = read("data/seoul/site_history.csv", dtype=str, usecols=["site_key"])
    need(sites, ["site_key", "permits_10y", "max_concurrent"], "sites")
    if sites.site_key.duplicated().any() or not set(hist.site_key) <= set(sites.site_key):
        raise ValidationError("sites: site_key 가 중복이거나 이력의 자리가 sites 에 없습니다")
    log.info("검증 통과: 행정동 %d, 역 %d, 자리 %d, 이력 %d", len(codes), len(dem), len(sites), len(hist))


# ---------------------------------------------------------------------- 실행
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-date", type=date.fromisoformat, help="기준일 (기본: 지난달 말일, 한국 시간)")
    ap.add_argument("--trigger", default="local", choices=["schedule", "manual", "local"])
    ap.add_argument("--no-load", action="store_true", help="계산·검증만 하고 DB는 건드리지 않음")
    ap.add_argument("--skip-fetch", action="store_true", help="data/raw 에 있는 CSV를 그대로 씀")
    ap.add_argument("--from-json", help="API 대신 이 폴더의 LOCALDATA_*.json 사용 (시험용)")
    ap.add_argument("--subway-cache", help="지하철 원본을 저장하고 다시 쓸 폴더 (기본: 실행할 때만 쓰는 임시 폴더)")
    a = ap.parse_args()
    a.base_date = a.base_date or last_month_end(datetime.now(KST).date())
    env = {**os.environ, "WTO_BASE_DATE": a.base_date.isoformat(), "PYTHONPATH": str(ROOT / "jari")}
    log.info("기준일 %s", a.base_date)

    load = not a.no_load
    if load and not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL 이 없습니다. 계산만 하려면 --no-load")
    runner = None
    if load:
        sys.path.insert(0, str(ROOT / "backend"))
        os.chdir(ROOT / "backend")  # load_data·load_sites 가 backend 폴더 기준으로 import 된다
        from batch_load import BatchRunner  # noqa: E402
        runner = BatchRunner(a.trigger, a.base_date, None, None)
        os.chdir(ROOT)

    def stage(name):
        if runner:
            runner.stage(name)
        else:
            log.info("단계 시작: %s", name)

    def body():
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            stage("fetch")
            start, end = demand_window(a.base_date, probe=True)
            env.update(WTO_DEMAND_START=start.strftime("%Y%m%d"), WTO_DEMAND_END=end.strftime("%Y%m%d"))
            log.info("수요 기간 %s ~ %s", start, end)
            if runner:
                runner.set_demand(start, end)
            step_fetch(a, env)
            stage("prepare"); step_prepare(a, env, tmp)
            stage("axes"); step_axes(a, env, tmp)
            stage("validate"); step_validate(a)
        if runner:
            stage("load"); runner.load()

    if runner is None:
        body()
    else:
        with runner:
            if runner.skipped:
                log.warning("다른 배치가 실행 중이라 건너뜁니다")
                return
            body()
    log.info("배치 완료 (기준일 %s)", a.base_date)


if __name__ == "__main__":
    main()
