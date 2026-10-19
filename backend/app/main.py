import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import log_requests
from app.routers import address, categories, data, dongs, health, reports, sites

settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="where to open API",
    description="공공데이터로 보는 소규모 창업 입지 리포트. 기준일 " + settings.base_date.isoformat(),
    version="0.1.0",
)

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
