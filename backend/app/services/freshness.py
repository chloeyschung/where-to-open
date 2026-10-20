"""지금 DB 데이터의 기준일과 갱신 일정.

기준일은 마지막으로 성공한 월 배치(batch_run)의 기준일이다. 배치가 한 번도 성공하지 않았으면
처음 손으로 적재한 데이터의 기준일(설정값 BASE_DATE, 기본 2026-09-30)을 쓴다.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.data_repo import DataRepository

KST = timezone(timedelta(hours=9))
SCHEDULE = "매월 1일 09:00 (한국 시간) 자동 갱신. 실패하면 7일까지 매일 09:00에 다시 시도"
RETRY_DAYS = 7  # .github/workflows/monthly-refresh.yml 의 cron '1-7' 과 같아야 한다

# batch/run.py 의 단계 이름과 같아야 한다
STAGES = [
    ("fetch", "수집", "서울 열린데이터광장 Open API에서 인허가 3종과 지하철 승하차를 받습니다."),
    ("prepare", "정규화", "공용 파일을 만들고 좌표·주소로 행정동을 붙이고 팝업을 표시합니다."),
    ("axes", "집계", "경쟁·안정성·자리·수요 지표를 기준일(지난달 말일)로 계산합니다."),
    ("validate", "검증", "파일·컬럼·행 수·코드가 맞는지 검사합니다. 실패하면 DB를 바꾸지 않습니다."),
    ("load", "적재", "임시 표에 넣고 한 트랜잭션으로 교체합니다. 실패하면 기존 데이터를 그대로 둡니다."),
]


def current_base_date(db: Session) -> date:
    run = DataRepository(db).last_success()
    return run.base_date if run and run.base_date else get_settings().base_date


def demand_window(db: Session) -> tuple[date, date]:
    run = DataRepository(db).last_success()
    if run and run.demand_start and run.demand_end:
        return run.demand_start, run.demand_end
    return date(2024, 9, 1), date(2026, 9, 30)  # 처음 적재한 수요 파일 기간


def last_month_end(today: date) -> date:
    return today.replace(day=1) - timedelta(days=1)


def next_scheduled_run(done_base: date | None, now: datetime | None = None) -> datetime:
    """다음 예약 실행 시각 (KST). .github/workflows/monthly-refresh.yml 의 cron 과 같아야 한다.

    배치는 매월 1~7일 매일 09:00에 깨어나, 이번 기준일(지난달 말일)이 이미 성공했으면 바로 끝난다.
    그래서 이번 달 기준일이 성공했으면 다음 달 1일, 아직이면 7일까지 남은 가장 가까운 09:00.
    done_base: 마지막으로 성공한 배치의 기준일
    """
    now = (now or datetime.now(KST)).astimezone(KST)
    target = last_month_end(now.date())
    if done_base is None or done_base < target:
        for day in range(1, RETRY_DAYS + 1):
            t = datetime(now.year, now.month, day, 9, 0, tzinfo=KST)
            if t > now:
                return t
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, 1, 9, 0, tzinfo=KST)
