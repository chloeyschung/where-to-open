# 경쟁 (재림)

서울 지방행정 인허가 데이터를 정제해 행정동별 업종 밀도를 계산합니다. 업종은 카페, 제과점, 한식입니다.
정제 중간에 거르기 전 공용 파일(`permits_base.csv`)을 저장해 자리 축과 같은 데이터를 씁니다.

## 데이터 출처

| 파일 | 데이터 | 제공 | 기준 |
|---|---|---|---|
| `cafe.csv` | 서울시 휴게음식점 인허가 정보 (`LOCALDATA_072405`) | 서울 열린데이터광장 (data.seoul.go.kr) | 2026-10-13 내려받음 |
| `bakery.csv` | 서울시 제과점영업 인허가 정보 (`LOCALDATA_072218`) | 서울 열린데이터광장 | 2026-10-13 내려받음 |
| `restaurant.csv` | 서울시 일반음식점 인허가 정보 (`LOCALDATA_072404`) | 서울 열린데이터광장 | 2026-10-13 내려받음 |
| `HangJeongDong_ver20260701.geojson` | 행정동 경계 | github.com/vuski/admdongkor | 2026-07-01 행정구역 |
| `jari/dong_fill.csv` | 좌표 없는 업소의 행정동 (주소 기준) | 자리 축 (`jari/fill_dong.py`, 행정안전부 도로명주소 검색API) | main 최신본 (PR #2) |

원본 인허가 데이터는 행정안전부 지방행정 인허가 데이터를 서울시가 제공하는 것으로, 원본 기준 3일 전 자료입니다.
공통 규칙(`docs/common-rules.md`) 1에 따라 발표까지 원본을 다시 받지 않습니다.
원본 파일과 행정동 경계는 용량 때문에 저장소에 올리지 않습니다.

## 실행

```bash
pip install -r requirements.txt
python permits_prep.py --cafe cafe.csv --bakery bakery.csv --restaurant restaurant.csv \
  --dong HangJeongDong_ver20260701.geojson --fill ../jari/dong_fill.csv --repo ..
```

`--asof`(기본 2026-09-30)는 공통 규칙 2의 기준일입니다.
`--repo 저장소폴더`를 주면 `stability/temp_rule.py`의 `flag_temporary()`로 팝업·행사 매장(`is_temp`)을 판정합니다(공통 규칙 5).

## 처리 순서

1. 세 파일을 읽어 합침 (cp949, 깨진 글자 몇 개는 �로 대체)
2. 서울 주소만 남김, 같은 파일 안 중복 관리번호 제거, 폐업일이 인허가일보다 앞선 행 제거
3. 좌표 변환: 중부원점 TM(EPSG:5174) → 위경도(WGS84)
4. 행정동 배정
   - 위경도를 행정동 경계와 겹쳐 배정 (`dong_via = coord`)
   - 좌표가 없는 업소는 자리 축이 주소로 찾은 행정동으로 채움 (`dong_via = jibun / road`)
5. 표시 열 추가 (지우지 않음)
   - `close_date_missing`: 폐업인데 폐업일이 빈 가게 (31곳, 공통 규칙 4)
   - `is_temp`: 팝업·행사 매장 (공통 규칙 5, 안정성 축 판정 함수)
6. 공용 파일 저장 (거르기 전)
7. 업종 분류 후 기준일(2026-09-30)에 영업중인 곳만 남겨 행정동별 밀도 계산
   - 인허가일 ≤ 2026-09-30, 폐업일이 비었거나 2026-09-30 뒤, `close_date_missing` 아님, `is_temp` 아님

## 업종 분류

| 업종 | 기준 |
|---|---|
| 카페 | 휴게음식점 중 업태 커피숍·다방·전통찻집 + 일반음식점 중 업태 '까페' |
| 제과점 | 제과점영업 전체 |
| 한식 | 일반음식점 중 업태 한식 |

## 결과 파일

| 파일 | 저장소 | 내용 |
|---|---|---|
| `dong_area.csv` | O | 서울 행정동 기준표 427개. `adm_cd`(행안부 10자리), `adm_cd8`(앞 8자리), `stat_cd`(통계청), 면적 km² |
| `competition_by_dong.csv` | O | 행정동 × 업종별 영업중 점포 수, 밀도(개/km²) |
| `uptae_counts.csv` | O | 원본 파일별 업태 건수 |
| `permits_base.csv` | X (186MB, 드라이브 공유) | 공용 파일. 폐업 포함, 모든 업태 |
| `competition_open.csv` | X (21MB) | 카페·제과점·한식 중 기준일 영업중 |

`permits_base.csv` 컬럼: `mgt_no`, `name`, `uptae`, `permit_date`, `close_date`, `status`, `jibun_addr`, `road_addr`, `lon`, `lat`, `adm_cd`, `adm_nm`, `dong_via`, `gu`, `source`, `category`, `is_open`, `close_date_missing`, `is_temp`
업소 키는 `source` + `mgt_no` (관리번호는 원본 파일 안에서만 고유).
`is_open`은 원본 영업상태 기준(내려받은 날)입니다. 기준일 영업 여부는 위 7번 조건으로 계산하세요.

## 서울 전체 결과

- 공용 파일 703,315곳 (영업중 161,435, 폐업 등 541,880)
- 행정동 배정: 좌표 638,138곳 + 주소 보충 28,895곳. 남은 빈칸 36,282곳 (영업중 935곳)
- 경쟁용 기준일 영업중: 한식 50,592 / 카페 17,012 / 제과점 4,276
- 팝업·행사 매장(`is_temp`) 19,932곳, 폐업일 없는 폐업(`close_date_missing`) 31곳. 둘 다 기준일 영업중에는 원래 해당 없어 경쟁 밀도는 변하지 않음
- 카페 밀도 상위: 명동, 서교동, 광희동, 을지로동, 대치4동

## 한계

- 영업중인데 좌표와 주소로 모두 행정동을 못 찾은 935곳은 밀도 계산에서 빠짐
- 휴게음식점 '기타 휴게음식점'(약 2만 8천 건)에 카페가 섞여 있을 수 있으나 업태만으로 구분할 수 없어 제외
- 밀도는 행정동 전체 면적 기준이라 산·하천이 넓은 동은 낮게 나옴
