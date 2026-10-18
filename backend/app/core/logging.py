"""요청·응답 로깅 미들웨어. 모든 요청이 Router 전후로 여기를 지나간다.

    2026-10-17 22:10:03 INFO app >>> GET /api/dongs?gu=종로구
    2026-10-17 22:10:03 INFO app <<< 200 GET /api/dongs 4.2ms
"""
import logging
import time

from fastapi import Request

logger = logging.getLogger("app")


async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    query = f"?{request.url.query}" if request.url.query else ""
    logger.info(">>> %s %s%s", request.method, request.url.path, query)  # 요청 (Router 실행 전)

    response = await call_next(request)  # Router → Service → DB 실행

    ms = (time.perf_counter() - start) * 1000
    logger.info("<<< %d %s %s %.1fms", response.status_code, request.method, request.url.path, ms)  # 응답
    return response
