"""월 배치의 DB 쪽: 실행 기록, 중복 실행 방지, 검증 후 한 번에 교체.

batch/run.py 가 부른다. 직접 실행하지 않는다.

- 중복 실행 방지: PostgreSQL advisory lock. 이미 다른 배치가 잡고 있으면 이번 실행은 skipped 로 기록하고 끝낸다.
  (GitHub Actions 의 concurrency 설정과 함께, 실행 위치가 여러 곳이어도 DB 교체는 한 번에 하나만 한다)
  계산하는 수십 분 동안 잠금 연결이 끊길 수 있어, 교체 직전에 연결을 확인하고 끊겼으면 다시 잠근다.
- 잠금을 잡았는데 running 으로 남은 예전 기록은 중간에 강제 종료된 것이라 failed 로 바꾼다.
- 실행 기록: batch_run 표. 시작할 때 running, 단계마다 stage, 끝나면 success / failed.
  기록은 교체 트랜잭션과 다른 짧은 트랜잭션으로 써서, 교체가 롤백돼도 실패 기록은 남는다.
- 교체: 새 데이터를 임시 표(stg_*)에 넣고 검증한 뒤, 한 트랜잭션 안에서 기존 행을 지우고 새 행을 넣는다.
  중간에 하나라도 실패하면 전체가 롤백돼 기존 데이터가 그대로 남는다. 커밋 전까지 API는 기존 데이터를 읽는다.
- 행정동·업종 표(dong, category)는 바꾸지 않는다. 새로 만든 행정동 기준표가 지금 DB와 다르면 교체하지 않고 실패로 남긴다.
"""
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

import load_data
import load_sites
from app.core.database import engine
from app.models import (
    BatchRun,
    Category,
    CompetitionStat,
    Dong,
    Site,
    SiteStore,
    StabilityAggregateStat,
    StabilityStat,
    StoreDong,
    SubwayStationStat,
    UptaeCount,
)

log = logging.getLogger("batch")
LOCK_KEY = 4270930  # 이 배치 전용 advisory lock 번호 (아무 정수)
MIN_RATIO = 0.9  # 새 행 수가 지금의 90%보다 적으면 원천이 잘못 받힌 것으로 보고 교체하지 않는다

# 부모 → 자식 순서 (넣을 때 이 순서, 지울 때 반대 순서)
REPLACE = [CompetitionStat, StabilityStat, StabilityAggregateStat, SubwayStationStat, StoreDong, UptaeCount, Site, SiteStore]


def now():
    return datetime.now(timezone.utc)


class BatchError(Exception):
    pass


def already_done(base_date: date) -> bool:
    """이 기준일로 이미 성공한 배치가 있으면 True (매월 1~7일 재시도 중 이미 끝난 달은 건너뛰려고)."""
    BatchRun.__table__.create(engine, checkfirst=True)
    with engine.connect() as c:
        last = c.execute(select(func.max(BatchRun.base_date)).where(BatchRun.status == "success")).scalar()
    return last is not None and last >= base_date


class BatchRunner:
    def __init__(self, trigger: str, base_date: date, demand_start: date | None, demand_end: date | None):
        self.trigger, self.base_date = trigger, base_date
        self.demand_start, self.demand_end = demand_start, demand_end
        self.run_id: int | None = None
        self.skipped = False
        self.conn = None

    # ------------------------------------------------------------------ 기록
    def _write(self, **values):
        with engine.begin() as c:
            c.execute(update(BatchRun).where(BatchRun.id == self.run_id).values(**values))

    def __enter__(self):
        BatchRun.__table__.create(engine, checkfirst=True)
        self.conn = engine.connect()
        got = self._try_lock()
        with engine.begin() as c:
            if got:  # 잠금을 잡았으니 지금 도는 다른 배치는 없다. running 으로 남은 기록은 강제 종료된 것
                c.execute(update(BatchRun).where(BatchRun.status == "running").values(
                    status="failed", finished_at=now(), message="중간에 강제 종료됨 (시간 초과·취소)"))
            self.run_id = c.execute(
                BatchRun.__table__.insert().returning(BatchRun.id),
                {"started_at": now(), "status": "running" if got else "skipped", "trigger": self.trigger,
                 "base_date": self.base_date, "demand_start": self.demand_start, "demand_end": self.demand_end,
                 "finished_at": None if got else now(),
                 "message": None if got else "다른 배치가 실행 중이라 건너뜀"},
            ).scalar_one()
        self.skipped = not got
        return self

    def _try_lock(self) -> bool:
        got = self.conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        self.conn.commit()
        return bool(got)

    def _ensure_lock(self):
        """교체 직전: 잠금 연결이 아직 살아 있는지 확인. 끊겼으면(잠금도 풀림) 새 연결로 다시 잠근다."""
        try:
            self.conn.execute(text("SELECT 1"))
            self.conn.rollback()
            return
        except DBAPIError:
            log.warning("잠금 연결이 끊겨 다시 연결합니다")
            self.conn.invalidate()
            self.conn.close()
        self.conn = engine.connect()
        if not self._try_lock():
            raise BatchError("잠금 연결이 끊긴 사이 다른 배치가 잠금을 잡았습니다")

    def set_demand(self, start: date, end: date):
        self.demand_start, self.demand_end = start, end
        self._write(demand_start=start, demand_end=end)

    def stage(self, name: str):
        log.info("단계 시작: %s", name)
        self._write(stage=name)

    def fail(self, message: str):
        log.error("배치 실패: %s", message)
        self._write(status="failed", finished_at=now(), message=message[:4000])

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and not self.skipped:
            self.fail(f"{exc_type.__name__}: {exc}")
        if self.conn is not None:
            try:
                self.conn.rollback()  # 실패한 읽기가 남아 있으면 닫아야 잠금을 풀 수 있다
                if not self.skipped:
                    self.conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                    self.conn.commit()
            except DBAPIError:  # 연결이 이미 끊겼으면 잠금도 이미 풀렸다
                log.warning("잠금 연결이 이미 끊겨 있습니다")
            finally:
                self.conn.close()
        return False  # 예외는 그대로 올린다

    # ------------------------------------------------------------------ 데이터 준비
    def _gather(self) -> dict[Any, list[dict]]:
        datasets = load_data.load_source_rows()  # CSV 형식·코드 검사 포함
        rows = {m: datasets[m] for m in REPLACE if m in datasets}
        rows[UptaeCount] = [{"id": i, **r} for i, r in enumerate(rows[UptaeCount], start=1)]

        # 자리: site_key 가 같으면 지금 id 를 그대로 쓴다 (화면이 들고 있는 id 가 갑자기 바뀌지 않게)
        old = dict(self.conn.execute(select(Site.site_key, Site.id)).all())
        next_id = (max(old.values()) if old else 0) + 1
        sites, ids = [], {}
        for batch in load_sites.site_batches():
            for r in batch:
                if r["site_key"] in ids:
                    raise BatchError(f"sites.csv 에 같은 site_key 가 두 번 있습니다: {r['site_key']}")
                sid = old.get(r["site_key"])
                if sid is None:
                    sid, next_id = next_id, next_id + 1
                ids[r["site_key"]] = sid
                sites.append({"id": sid, **r})
        history = [r for batch in load_sites.history_batches(ids) for r in batch]
        rows[Site] = sites
        rows[SiteStore] = [{"id": i, **r} for i, r in enumerate(history, start=1)]
        return datasets, rows

    def _check(self, datasets, rows):
        # 행정동·업종 기준표가 지금 DB와 같아야 한다
        cur_dong = {tuple(r) for r in self.conn.execute(select(Dong.adm_cd, Dong.name, Dong.gu)).all()}
        new_dong = {(r["adm_cd"], r["name"], r["gu"]) for r in datasets[Dong]}
        if cur_dong and cur_dong != new_dong:
            raise BatchError(f"행정동 기준표가 지금 DB와 다릅니다 (지금 {len(cur_dong)}, 새 {len(new_dong)}). 수동 확인이 필요합니다")
        cur_cat = set(self.conn.execute(select(Category.code)).scalars())
        if cur_cat and cur_cat != {r["code"] for r in datasets[Category]}:
            raise BatchError("업종 표가 지금 DB와 다릅니다")
        # 행 수가 갑자기 줄면 원천을 덜 받은 것으로 본다
        for model in REPLACE:
            cur = self.conn.execute(select(func.count()).select_from(model)).scalar() or 0
            new = len(rows[model])
            if new == 0:
                raise BatchError(f"{model.__tablename__}: 새 행이 0개입니다")
            if cur and new < cur * MIN_RATIO:
                raise BatchError(f"{model.__tablename__}: 새 행 {new:,}개가 지금 {cur:,}개의 {MIN_RATIO:.0%}보다 적습니다")

    # ------------------------------------------------------------------ 교체
    def load(self) -> dict[str, int]:
        self._ensure_lock()
        datasets, rows = self._gather()
        self._check(datasets, rows)
        self.conn.rollback()  # 검사용 읽기 트랜잭션을 닫고 교체 트랜잭션을 새로 연다
        counts = {m.__tablename__: len(rows[m]) for m in REPLACE}
        raw = self.conn.connection.driver_connection  # psycopg 연결 (COPY 용)
        with self.conn.begin():  # ← 이 블록 전체가 한 트랜잭션
            self.conn.execute(text("SET LOCAL statement_timeout = 0"))
            for model in REPLACE:
                t = model.__tablename__
                cols = [c.name for c in model.__table__.columns]
                self.conn.execute(text(f"CREATE TEMP TABLE stg_{t} (LIKE {t} INCLUDING DEFAULTS) ON COMMIT DROP"))
                with raw.cursor() as cur, cur.copy(f"COPY stg_{t} ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows[model]:
                        cp.write_row(tuple(r.get(c) for c in cols))
            # 임시 표 안에서 외래키 검사 (기존 표를 지우기 전에)
            bad = {
                "adm_cd": "SELECT count(*) FROM (SELECT adm_cd FROM stg_competition_stat UNION ALL SELECT adm_cd FROM stg_stability_stat"
                          " UNION ALL SELECT adm_cd FROM stg_subway_station_stat UNION ALL SELECT adm_cd FROM stg_store_dong"
                          " UNION ALL SELECT adm_cd FROM stg_site WHERE adm_cd IS NOT NULL) x WHERE adm_cd NOT IN (SELECT adm_cd FROM dong)",
                "site_id": "SELECT count(*) FROM stg_site_store WHERE site_id NOT IN (SELECT id FROM stg_site)",
            }
            for name, sql in bad.items():
                n = self.conn.execute(text(sql)).scalar()
                if n:
                    raise BatchError(f"임시 표 검사 실패: 맞는 짝이 없는 {name} {n:,}개")
            for model in reversed(REPLACE):
                self.conn.execute(text(f"DELETE FROM {model.__tablename__}"))
            for model in REPLACE:
                t = model.__tablename__
                cols = ", ".join(c.name for c in model.__table__.columns)
                self.conn.execute(text(f"INSERT INTO {t} ({cols}) SELECT {cols} FROM stg_{t}"))
            for t in ("site", "site_store", "uptae_count"):
                self.conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT COALESCE(max(id), 1) FROM {t}))"))
            # 성공 기록도 같은 트랜잭션에: 교체와 기록이 함께 반영되거나 함께 취소된다
            self.conn.execute(update(BatchRun).where(BatchRun.id == self.run_id).values(
                status="success", stage="load", finished_at=now(), row_counts=json.dumps(counts),
                message=f"기준일 {self.base_date} 데이터로 교체"))
        log.info("교체 완료: %s", counts)
        return counts
