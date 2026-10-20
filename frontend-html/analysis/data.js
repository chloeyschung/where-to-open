// build_data.py 가 만든 파일. 직접 고치지 말 것
window.ANALYSIS = {
 "overview": {
  "base_date": "2026-09-30",
  "dongs": 427,
  "permits_total": 703315,
  "permits_in_categories": 305983,
  "open_by_category": {
   "카페": 17012,
   "제과점": 4276,
   "한식": 50592
  },
  "open_total": 71880,
  "popups_removed": 19932,
  "popups_removed_in_categories": 4194,
  "close_date_missing": 31,
  "stations": 306,
  "sites_10y": 109943,
  "open_no_dong": 467
 },
 "sources": [
  {
   "name": "서울시 일반음식점 인허가 정보",
   "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
   "url": "https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do",
   "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072404(자리·안정성 축 수집)",
   "axes": "경쟁·안정성·자리"
  },
  {
   "name": "서울시 휴게음식점 인허가 정보",
   "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
   "url": "https://data.seoul.go.kr/dataList/OA-16095/S/1/datasetView.do",
   "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072405",
   "axes": "경쟁·안정성·자리"
  },
  {
   "name": "서울시 제과점영업 인허가 정보",
   "org": "서울특별시 (원천: 행정안전부 지방행정 인허가 데이터)",
   "url": "https://data.seoul.go.kr/dataList/OA-16084/S/1/datasetView.do",
   "method": "CSV 내려받기(공용 파일), Open API LOCALDATA_072218",
   "axes": "경쟁·안정성·자리"
  },
  {
   "name": "서울시 지하철호선별 역별 승하차 인원 정보 (일별)",
   "org": "서울특별시",
   "url": "https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do",
   "method": "월별 CSV 내려받기 (2024-09~2026-09)",
   "axes": "수요"
  },
  {
   "name": "서울시 지하철 호선별 역별 시간대별 승하차 인원 정보",
   "org": "서울특별시",
   "url": "https://data.seoul.go.kr/dataList/OA-12252/S/1/datasetView.do",
   "method": "Open API CardSubwayTime (2024-09~2026-09)",
   "axes": "수요"
  },
  {
   "name": "서울시 역사마스터 정보 (역 좌표)",
   "org": "서울특별시",
   "url": "https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do",
   "method": "파일",
   "axes": "수요 (역 → 행정동)"
  },
  {
   "name": "도로명주소 검색 API",
   "org": "행정안전부",
   "url": "https://business.juso.go.kr",
   "method": "Open API (지번·도로명주소 → 행정동)",
   "axes": "자리 (좌표 없는 가게 행정동 채우기)"
  },
  {
   "name": "행정동 경계 (admdongkor ver20260701)",
   "org": "vuski/admdongkor (GitHub)",
   "url": "https://github.com/vuski/admdongkor",
   "method": "파일 (2026-07-01 행정구역)",
   "axes": "전체 (좌표 → 행정동, 면적)"
  },
  {
   "name": "소상공인시장진흥공단 상가(상권)정보 (2026-06)",
   "org": "소상공인시장진흥공단",
   "url": "https://www.data.go.kr/data/15083033/fileData.do",
   "method": "파일 (검증용: 신고 없이 닫은 가게 규모 확인)",
   "axes": "자리 (검증)"
  }
 ],
 "competition": {
  "카페": [
   {
    "dong": "중구 명동",
    "density": 296.2,
    "count": 298
   },
   {
    "dong": "마포구 서교동",
    "density": 220.5,
    "count": 363
   },
   {
    "dong": "중구 광희동",
    "density": 198.1,
    "count": 149
   },
   {
    "dong": "중구 을지로동",
    "density": 173.6,
    "count": 104
   },
   {
    "dong": "강남구 대치4동",
    "density": 172.2,
    "count": 121
   },
   {
    "dong": "강남구 역삼1동",
    "density": 170.0,
    "count": 402
   },
   {
    "dong": "중구 소공동",
    "density": 152.9,
    "count": 143
   },
   {
    "dong": "중구 회현동",
    "density": 152.4,
    "count": 136
   },
   {
    "dong": "마포구 연남동",
    "density": 146.9,
    "count": 95
   },
   {
    "dong": "중구 신당동",
    "density": 125.7,
    "count": 68
   }
  ],
  "제과점": [
   {
    "dong": "마포구 연남동",
    "density": 88.1,
    "count": 57
   },
   {
    "dong": "송파구 송파1동",
    "density": 46.0,
    "count": 32
   },
   {
    "dong": "마포구 서교동",
    "density": 42.5,
    "count": 70
   },
   {
    "dong": "강동구 성내3동",
    "density": 35.8,
    "count": 23
   },
   {
    "dong": "서초구 반포4동",
    "density": 32.9,
    "count": 48
   },
   {
    "dong": "중구 회현동",
    "density": 32.5,
    "count": 29
   },
   {
    "dong": "중구 황학동",
    "density": 31.8,
    "count": 10
   },
   {
    "dong": "강남구 신사동",
    "density": 31.6,
    "count": 55
   },
   {
    "dong": "강동구 성내1동",
    "density": 30.3,
    "count": 20
   },
   {
    "dong": "관악구 중앙동",
    "density": 29.0,
    "count": 11
   }
  ],
  "한식": [
   {
    "dong": "중구 황학동",
    "density": 546.7,
    "count": 172
   },
   {
    "dong": "중구 명동",
    "density": 489.0,
    "count": 492
   },
   {
    "dong": "강남구 역삼1동",
    "density": 481.6,
    "count": 1139
   },
   {
    "dong": "중구 을지로동",
    "density": 475.7,
    "count": 285
   },
   {
    "dong": "종로구 종로1·2·3·4가동",
    "density": 467.3,
    "count": 1118
   },
   {
    "dong": "종로구 종로5·6가동",
    "density": 461.3,
    "count": 292
   },
   {
    "dong": "강남구 대치4동",
    "density": 451.2,
    "count": 317
   },
   {
    "dong": "관악구 신림동",
    "density": 427.8,
    "count": 217
   },
   {
    "dong": "송파구 방이2동",
    "density": 422.4,
    "count": 324
   },
   {
    "dong": "노원구 상계2동",
    "density": 406.4,
    "count": 240
   }
  ]
 },
 "stability": [
  {
   "category": "카페",
   "open": 17012,
   "turnover": 11.5,
   "new_rate": 9.9,
   "survival_3y": 62.7,
   "closed_1y": 1995,
   "new_1y": 1712
  },
  {
   "category": "제과점",
   "open": 4276,
   "turnover": 13.6,
   "new_rate": 17.1,
   "survival_3y": 60.2,
   "closed_1y": 560,
   "new_1y": 707
  },
  {
   "category": "한식",
   "open": 50592,
   "turnover": 9.6,
   "new_rate": 7.9,
   "survival_3y": 61.2,
   "closed_1y": 4950,
   "new_1y": 4063
  }
 ],
 "stability_dong_share": {
  "카페": {
   "turnover_dong": 286,
   "survival_dong": 243,
   "dongs": 427
  },
  "제과점": {
   "turnover_dong": 41,
   "survival_dong": 25,
   "dongs": 427
  },
  "한식": {
   "turnover_dong": 398,
   "survival_dong": 332,
   "dongs": 427
  }
 },
 "jari": {
  "sites_10y": 109943,
  "single_sites": 61878,
  "single_avg": 0.65,
  "single_4plus": 363,
  "distribution": [
   {
    "permits": 0,
    "label": "0건",
    "sites": 30763
   },
   {
    "permits": 1,
    "label": "1건",
    "sites": 23925
   },
   {
    "permits": 2,
    "label": "2건",
    "sites": 5544
   },
   {
    "permits": 3,
    "label": "3건",
    "sites": 1283
   },
   {
    "permits": 4,
    "label": "4건",
    "sites": 282
   },
   {
    "permits": 5,
    "label": "5건",
    "sites": 65
   },
   {
    "permits": 6,
    "label": "6건 이상",
    "sites": 16
   }
  ],
  "demo": {
   "site": "중구 황학동 479",
   "dong": "황학동",
   "permits_10y": 9,
   "dong_avg_single": 0.68,
   "history": [
    {
     "name": "기쁨광주리",
     "uptae": "한식",
     "opened": "2002-02-02",
     "closed": "2016-10-17",
     "months": 176
    },
    {
     "name": "숙성김치찌개",
     "uptae": "한식",
     "opened": "2016-10-17",
     "closed": "2016-11-25",
     "months": 1
    },
    {
     "name": "사케요부",
     "uptae": "기타",
     "opened": "2016-11-29",
     "closed": "2017-03-28",
     "months": 4
    },
    {
     "name": "꼬꼬꿀꿀",
     "uptae": "한식",
     "opened": "2017-04-24",
     "closed": "2018-06-29",
     "months": 14
    },
    {
     "name": "피노키오",
     "uptae": "분식",
     "opened": "2018-07-04",
     "closed": "2018-12-31",
     "months": 6
    },
    {
     "name": "족발의장인 동대문점",
     "uptae": "기타",
     "opened": "2019-01-24",
     "closed": "2019-03-25",
     "months": 2
    },
    {
     "name": "심야방독",
     "uptae": "중국식",
     "opened": "2019-05-02",
     "closed": "2019-11-29",
     "months": 7
    },
    {
     "name": "해피딜리버리",
     "uptae": "한식",
     "opened": "2019-12-02",
     "closed": "2020-02-14",
     "months": 2
    },
    {
     "name": "딜리버링",
     "uptae": "한식",
     "opened": "2020-06-01",
     "closed": "2022-06-17",
     "months": 25
    },
    {
     "name": "마라샤오반",
     "uptae": "중국식",
     "opened": "2022-07-11",
     "closed": "",
     "months": 51
    }
   ]
  },
  "top_per_slot": [
   {
    "site": "중구 황학동 479",
    "dong": "황학동",
    "per_slot": 9.0,
    "permits": 9
   },
   {
    "site": "영등포구 문래동3가 55-6",
    "dong": "문래동",
    "per_slot": 8.0,
    "permits": 8
   },
   {
    "site": "관악구 신림동 619-27",
    "dong": "난곡동",
    "per_slot": 7.0,
    "permits": 7
   },
   {
    "site": "영등포구 도림동 254",
    "dong": "도림동",
    "per_slot": 7.0,
    "permits": 7
   },
   {
    "site": "송파구 오금동 146-5",
    "dong": "오금동",
    "per_slot": 7.0,
    "permits": 7
   }
  ]
 },
 "demand": {
  "stations": 306,
  "dongs_with_station": 225,
  "top": [
   {
    "station": "서울역",
    "where": "중구 회현동",
    "weekly": 222337,
    "weekday": 233472,
    "weekend": 194498
   },
   {
    "station": "잠실(송파구청)",
    "where": "송파구 잠실6동",
    "weekly": 199430,
    "weekday": 207056,
    "weekend": 180365
   },
   {
    "station": "홍대입구",
    "where": "마포구 서교동",
    "weekly": 189988,
    "weekday": 182741,
    "weekend": 208106
   },
   {
    "station": "고속터미널",
    "where": "서초구 반포4동",
    "weekly": 170916,
    "weekday": 166881,
    "weekend": 181004
   },
   {
    "station": "강남",
    "where": "강남구 역삼1동",
    "weekly": 151560,
    "weekday": 172382,
    "weekend": 99505
   },
   {
    "station": "사당",
    "where": "동작구 사당1동",
    "weekly": 134744,
    "weekday": 143120,
    "weekend": 113803
   },
   {
    "station": "선릉",
    "where": "강남구 삼성2동",
    "weekly": 125941,
    "weekday": 154203,
    "weekend": 55287
   },
   {
    "station": "신림",
    "where": "관악구 신림동",
    "weekly": 111449,
    "weekday": 120327,
    "weekend": 89252
   },
   {
    "station": "여의도",
    "where": "영등포구 여의동",
    "weekly": 111143,
    "weekday": 132470,
    "weekend": 57824
   },
   {
    "station": "가산디지털단지",
    "where": "금천구 가산동",
    "weekly": 109426,
    "weekday": 137441,
    "weekend": 39388
   }
  ],
  "office": [
   {
    "station": "종각",
    "where": "종로구 종로1·2·3·4가동",
    "ratio": 21.8
   },
   {
    "station": "시청",
    "where": "중구 소공동",
    "ratio": 18.1
   },
   {
    "station": "광화문(세종문화회관)",
    "where": "종로구 종로1·2·3·4가동",
    "ratio": 16.7
   },
   {
    "station": "국회의사당",
    "where": "영등포구 여의동",
    "ratio": 15.5
   },
   {
    "station": "을지로입구",
    "where": "중구 명동",
    "ratio": 15.4
   }
  ],
  "weekend": [
   {
    "station": "올림픽공원(한국체대)",
    "where": "송파구 오륜동",
    "ratio": 1.45
   },
   {
    "station": "동묘앞",
    "where": "종로구 창신1동",
    "ratio": 1.24
   },
   {
    "station": "용산",
    "where": "용산구 한강로동",
    "ratio": 1.14
   },
   {
    "station": "홍대입구",
    "where": "마포구 서교동",
    "ratio": 1.14
   },
   {
    "station": "이태원",
    "where": "용산구 이태원1동",
    "ratio": 1.12
   }
  ],
  "min_weekday_for_types": 20000
 }
};
