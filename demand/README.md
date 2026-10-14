# 지하철 수요 데이터

지하철 승하차 자료를 역별로 집계하고, 역 좌표를 행정동 경계와 연결해 최종 수요 CSV에 행정동 정보를 추가합니다.

## 폴더 구조

```text
demand/
|-- data/
|   |-- HangJeongDong_ver20260701.geojson
|   |-- dong_area.csv
|   `-- 서울시 역사마스터 정보.json
|-- map_stations_to_dongs.py
|-- requirements.txt
|-- station_dong_mapping.csv       # 생성되는 역-행정동 매핑 결과
|-- station_dong_overrides.csv     # 수동 매핑 입력
|-- subway.py
`-- subway_demand_202409_202609.csv # 최종 역별 수요 데이터
```

`data/`의 입력 파일은 저장소에 포함되어 있으므로 별도 경로 인자 없이 사용할 수 있습니다.

## 설치 및 설정

`demand` 디렉터리에서 의존성을 설치합니다.

```powershell
python -m pip install -r requirements.txt
```

`subway.py`는 서울 열린데이터광장 API 키가 필요합니다. 로컬에 `.env` 파일을 만들고 다음 항목을 설정하세요. `.env`는 Git에 올리지 않습니다.

```text
SEOUL_OPENAPI_KEY=발급받은_API_키
```

## 실행 순서

```powershell
python .\subway.py
python .\map_stations_to_dongs.py
```

먼저 `subway.py`가 기간별 지하철 데이터를 모아 역별 기본 수요 CSV를 생성합니다. 다음으로 `map_stations_to_dongs.py`가 좌표와 행정동 경계를 사용해 매핑 결과를 만들고, 최종 수요 CSV에 행정동 정보를 붙입니다. 수요 데이터를 새로 생성했다면 두 명령을 순서대로 실행하세요.

## 수동 매핑

`station_dong_overrides.csv`에서 역별 수동 지정값을 관리합니다.

| 컬럼 | 용도 |
|---|---|
| `SUB_STA_NM` | 수요 CSV의 역명 |
| `adm_cd` | `data/dong_area.csv`에 있는 행안부 10자리 행정동 코드 |
| `reason` | 수동 지정 근거 |

`adm_cd`는 기준표에 존재하는 코드여야 하며, `reason`은 필수입니다. 스크립트는 실행 시 코드에 해당하는 행정동명과 구를 기준표에서 채웁니다.

## 산출물

- `station_dong_mapping.csv`: 역별 좌표, 자동·수동 매핑 상태, 행정동 코드 및 검토 사유를 기록합니다.
- `subway_demand_202409_202609.csv`: 역별 수요 지표와 행정동 컬럼을 함께 저장합니다. 행정동 컬럼은 `SUB_STA_NM` 바로 뒤에 `adm_cd`, `adm_cd8`, `stat_cd`, `adm_nm`, `gu` 순서로 배치됩니다. 면적 컬럼은 포함하지 않습니다.

행정동이 연결되지 않은 역도 행을 삭제하지 않고, 행정동 관련 컬럼을 빈 값으로 둡니다.
