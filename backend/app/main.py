import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import log_requests
from app.models import BatchRun
from app.routers import address, categories, data, dongs, health, reports, sites

settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="where to open API",
    description="공공데이터로 보는 소규모 창업 입지 리포트. 데이터는 매월 1일 배치로 갱신하고, 기준일은 각 응답의 base_date에 있습니다.",
    version="0.1.0",
)

# 월 배치 기록 표가 없으면 만든다 (있으면 건드리지 않음). DB에 못 붙어도 앱은 뜨게 한다
try:
    BatchRun.__table__.create(engine, checkfirst=True)
except Exception:  # noqa: BLE001
    logging.getLogger("app").warning("batch_run 표를 확인하지 못했습니다. 기준일은 설정값을 씁니다", exc_info=True)

# CORS: 브라우저가 "다른 출처"의 응답을 읽어도 되는지 허락하는 헤더.
# 화면(frontend-html, Vercel)은 다른 주소에서 이 API를 직접 부르므로, 그 화면 주소를 CORS_ORIGINS에 넣는다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 모든 요청·응답을 로그로 남긴다 (app/core/logging.py)
app.middleware("http")(log_requests)

# 예외를 {"error": {...}} 형식으로 바꾼다 (app/core/exceptions.py)
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(categories.router)
app.include_router(reports.router)
app.include_router(dongs.router)
app.include_router(sites.router)
app.include_router(address.router)
app.include_router(data.router)
