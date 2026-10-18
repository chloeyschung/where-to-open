# 빌드 컨텍스트는 프로젝트 루트 (docker-compose.yml). 적재할 CSV가 competition/·jari/·stability/에 있어서다.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# REPO_DIR(= /app) 기준 경로를 프로젝트 폴더와 똑같이 맞춘다
COPY competition/dong_area.csv competition/competition_by_dong.csv competition/uptae_counts.csv /app/competition/
COPY jari/dong_fill.csv /app/jari/
COPY stability/category_map.csv /app/stability/
COPY backend/ .

EXPOSE 8000
ENTRYPOINT ["sh", "/app/backend/docker-entrypoint.sh"]
