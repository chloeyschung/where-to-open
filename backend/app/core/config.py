from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # 환경 변수 > backend/.env 순으로 읽는다. docker compose는 루트 .env를 환경 변수로 넘긴다
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str  # 기본값 없음. 없으면 앱이 뜨지 않는다 (예: postgresql+psycopg://user:pw@host:5432/where_to_open)
    cors_origins: str = ""  # 백엔드를 직접 부르는 프론트 주소. 쉼표로 구분, 비우면 CORS 헤더 없음
    base_date: date = date(2026, 9, 30)  # 공통 규칙 2
    sql_echo: bool = False  # true면 실행되는 SQL을 콘솔에 출력
    juso_api_key: str = ""  # 행정안전부 도로명주소 검색API 승인키. 비우면 주소 검색만 503


@lru_cache
def get_settings() -> Settings:
    return Settings()
