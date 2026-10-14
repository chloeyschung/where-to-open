# 경쟁 축 (재림)

서울 지방행정 인허가 데이터를 정제해 업종별 경쟁 밀도를 계산합니다.
업종: 카페 / 제과점 / 한식

## 원본 데이터 (저장소에는 올리지 않음)

| 파일 | 출처 |
|---|---|
| cafe.csv | 서울 열린데이터광장, 서울시 휴게음식점 인허가 정보 |
| bakery.csv | 서울 열린데이터광장, 서울시 제과점영업 인허가 정보 |
| restaurant.csv | 서울 열린데이터광장, 서울시 일반음식점 인허가 정보 |
| HangJeongDong_ver20260701.geojson | github.com/vuski/admdongkor (행정동 경계, 2026.07 기준) |

## 실행

```bash
pip install -r requirements.txt
python permits_prep.py --cafe cafe.csv --bakery bakery.csv --restaurant restaurant.csv \
    --dong HangJeongDong_ver20260701.geojson
```

## 결과 파일

| 파일 | 저장소 | 내용 |
|---|---|---|
| dong_area.csv | O | 서울 행정동 기준표 427개. adm_cd(행안부 10자리), adm_cd8(앞 8자리), stat_cd(통계청), 면적 km² |
| competition_by_dong.csv | O | 행정동 x 업종별 영업중 점포 수, 밀도(개/km²) |
| uptae_counts.csv | O | 원본 파일별 업태 건수 |
| permits_base.csv | X (181MB, 드라이브 공유) | 공용 파일. 폐업 포함, 모든 업태, 거르기 전. 자리 축과 공유 |
| competition_open.csv | X (21MB) | 카페·제과점·한식 중 영업중 |

## 정제 규칙

- 서울 주소만, 관리번호 중복 제거, 폐업일이 인허가일보다 앞선 행 제거
- 좌표: 중부원점 TM(EPSG:5174) → 위경도(WGS84)
- 행정동: 위경도를 행정동 경계와 겹쳐 배정, 면적은 경계에서 계산
- 카페: 휴게음식점 중 커피숍·다방·전통찻집 + 일반음식점 중 업태 '까페'
- 제과점: 제과점영업 전체
- 한식: 일반음식점 중 업태 한식

## 알려진 한계

- 영업중인데 좌표가 없는 업소 약 1만 2천 곳은 행정동 밀도 계산에서 빠짐
- 원본에 깨진 글자 몇 개가 섞여 있어 해당 글자는 �로 표시됨
