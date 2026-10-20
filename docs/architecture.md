# 서비스 아키텍처

현재 구성 기준: 2026-10-20. HTML/CSS/JavaScript 화면(`frontend-html`, Vercel), FastAPI 백엔드(Render), Supabase PostgreSQL로 구성합니다. 점선 흐름은 아직 구현·배포되지 않은 연결 또는 데이터입니다.

| 구성 | 플랫폼 | 주소 |
|---|---|---|
| 화면 | Vercel (`frontend-html` 폴더) | https://where-to-open-frontend-html.vercel.app (데이터 분석: https://where-to-open-frontend-html.vercel.app/analysis/) |
| API | Render Web Service (Docker, `backend/Dockerfile`) | https://where-to-open-cilr.onrender.com |
| API 문서 (Swagger UI) | Render | https://where-to-open-cilr.onrender.com/docs |
| DB | Supabase PostgreSQL (서울 리전) | 접속 정보는 Render 환경변수 `DATABASE_URL` |

`main` 브랜치에 머지하면 Render가 API를 다시 배포합니다.

## 서비스 요청 흐름

```mermaid
flowchart LR
    USER["창업 후보자<br/>동네 2~4곳 비교"]
    FRONT["HTML · CSS · JavaScript<br/>frontend-html<br/>Vercel"]
    API["FastAPI<br/>Render Web Service"]
    ROUTER["Routers<br/>요청 검증·경로 분기"]
    SERVICE["Services<br/>리포트·비교 응답 구성"]
    REPO["Repositories<br/>SQLAlchemy 조회"]
    DB[("Supabase PostgreSQL<br/>공통 행정동 코드 기준")]

    USER --> FRONT
    FRONT -->|HTTPS GET| API
    API --> ROUTER --> SERVICE --> REPO --> DB
    SERVICE -->|"HTTPS GET (주소 검색 때만)"| JUSO["행정안전부<br/>도로명주소 검색 API"]

    ROUTER --- R1["동네·업종 목록<br/>/api/dongs · /api/categories"]
    ROUTER --- R2["동네 비교·리포트<br/>/api/dongs/compare<br/>/api/dongs/{adm_cd}/report"]
    ROUTER --- R3["자리 상세<br/>/api/address/search → /api/sites/{site_id}"]
    ROUTER --- R4["데이터·파이프라인 설명<br/>/api/data/overview<br/>/api/data/pipeline"]

    DB --- POP["적재됨<br/>행정동·업종·경쟁·안정성<br/>역별 수요·자리 109,943<br/>자리 이력 576,785·출처"]
    DB -.-> EMPTY["데이터 미적재<br/>공용 permits_base.csv<br/>연도별 안정성·시간대별 동 수요"]
```

프론트엔드는 FastAPI만 호출합니다. Supabase 접속 문자열과 도로명주소 API 키(`JUSO_API_KEY`)는 backend 환경변수로만 관리하며 브라우저에 전달하지 않습니다. 화면이 다른 주소(Vercel)에서 API를 부르므로, 화면 주소를 API의 환경변수 `CORS_ORIGINS`에 넣어야 브라우저가 응답을 읽습니다.

외부 API를 요청 때마다 부르는 곳은 주소 검색(`GET /api/address/search`) 하나입니다. 입력한 주소를 도로명주소 API로 찾아 지번을 자리 키(`구 동 번지`, `jari/common.py`의 `jibun_key`와 같은 규칙)로 바꾸고 `site`와 `dong`에서 자리·행정동을 찾습니다. 나머지 API는 기준일(2026-09-30)로 미리 계산해 적재한 값만 읽습니다.

## 데이터 수집 흐름 (외부 API·오픈 데이터 → 축별 결과 파일)

기준일(2026-09-30)로 한 번 수집·계산해 결과 파일을 만듭니다. 서비스가 돌아가는 동안 다시 수집하지 않습니다.

```mermaid
flowchart LR
    subgraph EXT[외부 API · 오픈 데이터]
        P["서울 열린데이터광장<br/>인허가 3종 CSV<br/>(OA-16094·16095·16084)"]
        PAPI["서울 Open API<br/>LOCALDATA_072404·072405·072218"]
        SUBD["서울 열린데이터광장<br/>지하철 일별 승하차 CSV (OA-12914)"]
        SUBH["서울 Open API<br/>CardSubwayTime (OA-12252)"]
        STA["역사마스터 (OA-21232)"]
        JUSO["행정안전부<br/>도로명주소 검색 API"]
        BND["행정동 경계<br/>vuski/admdongkor"]
    end

    PAPI --> JC["jari/collect.py · hemd.py · fill_dong.py<br/>좌표 없는 가게의 행정동을 주소로 찾기"]
    JUSO --> JC
    JC --> FILL["jari/dong_fill.csv"]
    P --> PREP["competition/permits_prep.py<br/>정제 · 좌표 → 행정동 · 팝업 판정"]
    BND --> PREP
    FILL --> PREP
    PREP --> BASE["공용 파일 permits_base.csv<br/>(드라이브)"]
    PREP --> COMPOUT["competition_by_dong.csv · dong_area.csv"]
    BASE --> STABS["stability/build_stability.py"] --> STABOUT["stability_by_dong·gu·seoul.csv"]
    BASE --> SITES["jari/sites.py"] --> SITEOUT["sites.csv · site_history.csv<br/>(드라이브)"]
    SUBD --> SUB["demand/subway.py · map_stations_to_dongs.py"]
    SUBH --> SUB
    STA --> SUB
    BND --> SUB
    SUB --> DEMOUT["subway_demand_202409_202609.csv"]
```

## 데이터 적재 흐름 (결과 파일 → DB)

```mermaid
flowchart LR
    subgraph SOURCES[축별 결과 파일]
        COMP["competition/<br/>dong_area.csv<br/>competition_by_dong.csv<br/>uptae_counts.csv"]
        STAB["stability/data/<br/>stability_by_dong.csv<br/>stability_by_gu.csv<br/>stability_seoul.csv"]
        DEMAND["demand/<br/>subway_demand_202409_202609.csv<br/>역별 하루 평균 집계"]
        JARI["jari/<br/>dong_fill.csv<br/>주소 → 행정동 보충"]
        SITE["data/seoul/ (드라이브, git 제외)<br/>sites.csv · site_history.csv<br/>자리·업소 10년 이력"]
        MISSING["적재 안 함 (예비 표)<br/>permits_base.csv · yearly_by_dong.csv"]
    end

    COMP --> LOADER["backend/load_data.py<br/>CSV 검증·코드 매핑<br/>빈 DB에 스키마 생성·적재"]
    STAB --> LOADER
    DEMAND --> LOADER
    JARI --> LOADER
    SITE --> SITELOADER["backend/load_sites.py<br/>키 연결·중복 방지<br/>작은 트랜잭션으로 적재"]
    LOADER --> DB[("Supabase PostgreSQL")]
    SITELOADER --> DB
    MISSING -.->|적재 안 함| DB

    subgraph TABLES[적재된 테이블]
        T1["dong · category · meta_source (API는 쓰지 않음)"]
        T2["competition_stat · stability_stat<br/>stability_aggregate_stat"]
        T3["subway_station_stat · store_dong · uptae_count"]
        T4["site · site_store<br/>자리 109,943 · 이력 576,785"]
    end
    DB --> TABLES
```

`load_data.py --dry-run`은 CSV 형식과 행정동 코드 매핑을 검사하고, 실제 실행은 기존 애플리케이션 데이터가 없는 DB에서만 진행합니다. 수요 CSV는 역별 집계 자료이므로 `demand_stat`의 행정동×시간대 테이블에 잘못 넣지 않고 `subway_station_stat`에 적재합니다.

## 월간 갱신 (배치)

```mermaid
flowchart LR
    CRON["GitHub Actions<br/>매월 1~7일 09:00 KST<br/>(이미 성공한 달은 건너뜀) · 수동 실행"] --> RUN["batch/run.py<br/>fetch → prepare → axes → validate"]
    API2["서울 Open API<br/>인허가 3종 · 지하철"] --> RUN
    RUN -->|검증 통과| LOAD["backend/batch_load.py<br/>임시 표 → 한 트랜잭션 교체"]
    RUN -.->|실패| KEEP["DB 그대로<br/>batch_run 에 실패 기록"]
    LOAD --> DB2[("Supabase PostgreSQL")]
    LOAD --> LOG["batch_run<br/>실행 기록"]
    LOG --> SHOW["GET /api/data/pipeline<br/>화면 위 '기준일 ○○'"]
```

기준일은 지난달 말일입니다. 중복 실행은 GitHub Actions `concurrency`와 PostgreSQL advisory lock으로 막고, 실패하면 기존 데이터를 그대로 둡니다. 자세한 내용은 `batch/README.md`에 있습니다.

## 현재 제약

- `data/seoul/sites.csv`와 `data/seoul/site_history.csv`(드라이브에서 받기, git 제외)를 `backend/load_sites.py`로 적재했습니다. 자리 109,943건, 업소 이력 576,785건이며 주소 검색(`GET /api/address/search`)으로 `site_id`를 찾아 `GET /api/sites/{site_id}`에서 조회합니다.
- `store` 표는 적재하지 않았습니다(공용 `permits_base.csv`는 드라이브에 있음). 화면은 미리 계산한 지표만 씁니다.
- 데이터 출처 목록(`GET /api/data/overview`의 `sources`)은 DB `meta_source`(3개만 적재됨)가 아니라 `backend/app/services/data_service.py`에 둔 9개를 줍니다. 데이터 분석 페이지 목록과 같습니다.
- `yearly_stat` 산출물과 행정동×시간대 수요 파일은 현재 없습니다. 수요는 역별 집계의 오전·저녁·밤 지표를 씁니다.
- 수집 파이프라인 API는 단계 설명만 반환합니다. 배치 실행 이력이나 실제 작업 상태를 추적하는 기능은 아직 없습니다.
- 주소 검색은 도로명주소 API가 돌려준 앞쪽 20건만 봅니다. 결과가 많으면 주소를 더 자세히 넣어야 합니다. Render에 `JUSO_API_KEY`가 없으면 주소 검색만 503을 돌려줍니다.
