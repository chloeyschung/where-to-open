"""주소 검색: 사용자가 넣은 주소를 도로명주소 검색API로 찾아 자리(site)와 행정동에 연결한다.

이 API만 요청 때마다 외부 API를 부른다. 나머지 API는 기준일(9/30)로 미리 계산해 DB에 넣은 값만 읽는다.
자리 키는 자리 축(jari/common.py jibun_key)과 같은 규칙으로 만들어야 site 테이블의 site_key와 맞는다.
"""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, ExternalApiError, NotConfiguredError
from app.repositories.dong_repo import DongRepository
from app.repositories.site_repo import SiteRepository
from app.schemas.address import AddressMatch, AddressSearchResponse

logger = logging.getLogger("app")

JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
PAGE_SIZE = 20  # 화면에 보여 줄 후보 수. 더 좁히려면 사용자가 주소를 자세히 넣는다

# jari/common.py 와 같은 정규식. "서울특별시 마포구 망원동 329-1 2층" → ("마포구", "망원동", None, "329-1")
JIBUN_PAT = re.compile(r"^서울특별시 (\S+구) (\S+) (산\s*)?(\d+(?:-\d+)?)(?:\s|,|\(|$)")

# 도로명주소 API 오류 코드 중 사용자가 검색어를 고치면 되는 것 (나머지는 서버·키 문제)
USER_ERRORS = {"E0005", "E0006", "E0008", "E0009", "E0011", "E0012", "E0013", "E0015"}


def jibun_key(addr: str) -> str | None:
    """jari/common.py jibun_key 와 같은 규칙. 부번 0은 떼고("106-0" → "106"), 본번 0은 번지 모름(None)."""
    m = JIBUN_PAT.match(addr or "")
    if not m:
        return None
    main, _, sub = m.group(4).partition("-")
    main, sub = int(main), int(sub or 0)
    if main == 0:
        return None
    return f"{m.group(1)} {m.group(2)} {'산' if m.group(3) else ''}{main}{f'-{sub}' if sub else ''}"


def normalize_dong(name: str) -> str:
    """jari/fill_dong.py norm 과 같은 규칙. 도로명주소 API는 '망원제1동', 기준표는 '망원1동'처럼 쓰는 동이 있다."""
    return re.sub(r"제(\d)", r"\1", name, count=1).replace(".", "·")


class AddressService:
    def __init__(self, db: Session):
        self.sites = SiteRepository(db)
        self.dongs = DongRepository(db)
        self.key = get_settings().juso_api_key

    def search(self, q: str) -> AddressSearchResponse:
        if not self.key:
            raise NotConfiguredError("주소 검색을 쓸 수 없습니다. 서버에 JUSO_API_KEY가 없습니다.")
        total, rows = self._call_juso(q.strip())

        seoul, seen = [], set()
        for j in rows:
            if j.get("siNm") != "서울특별시":
                continue
            key = jibun_key(j.get("jibunAddr", ""))
            dedupe = key or j.get("jibunAddr")
            if dedupe in seen:  # 같은 지번에 건물이 여러 개면 자리는 하나
                continue
            seen.add(dedupe)
            seoul.append((j, key))

        found = self.sites.get_by_keys([k for _, k in seoul if k])
        items = []
        for j, key in seoul:
            site = found.get(key) if key else None
            adm_cd, dong_name, basis = self._dong(j, site)
            items.append(AddressMatch(
                jibun_addr=j.get("jibunAddr", ""),
                road_addr=j.get("roadAddr", ""),
                building=j.get("bdNm") or None,
                site_key=key,
                site_id=site.id if site else None,
                permits_10y=site.permits_10y if site else None,
                gu=j.get("sggNm", ""),
                adm_cd=adm_cd,
                dong=dong_name,
                dong_basis=basis,
            ))
        return AddressSearchResponse(query=q, total=total, truncated=total > len(rows), items=items)

    def _dong(self, j: dict, site) -> tuple[str | None, str | None, str | None]:
        # 자리 데이터에 있으면 그 행정동을 쓴다. 가게 좌표로 붙인 값이라 다른 축과 같은 동이 된다
        if site is not None and site.adm_cd:
            dong = self.dongs.get(site.adm_cd)
            return site.adm_cd, dong.name if dong else None, "site"
        # 없으면 도로명주소 API의 행정동 이름. "서울특별시 중구 황학동", 경계 주소는 "서강동,합정동" → 첫 번째
        parts = (j.get("hemdNm") or "").split()
        if len(parts) < 3:
            return None, None, None
        gu, name = parts[1], parts[-1].split(",")[0]
        dong = self.dongs.find_by_name(gu, name) or self.dongs.find_by_name(gu, normalize_dong(name))
        return (dong.adm_cd, dong.name, "juso") if dong else (None, None, None)

    def _call_juso(self, keyword: str) -> tuple[int, list[dict]]:
        url = JUSO_URL + "?" + urllib.parse.urlencode({
            "confmKey": self.key, "currentPage": 1, "countPerPage": PAGE_SIZE,
            "keyword": keyword, "resultType": "json", "addInfoYn": "Y",  # addInfoYn=Y → 행정동 이름(hemdNm)
        })
        try:
            with urllib.request.urlopen(url, timeout=10) as res:
                data = json.load(res)
            common = data["results"]["common"]
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            logger.warning("도로명주소 API 호출 실패: %s", exc)  # url에 키가 있어 남기지 않는다
            raise ExternalApiError("주소 검색 서비스에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.") from exc

        code = common.get("errorCode")
        if code != "0":
            logger.warning("도로명주소 API 오류 %s: %s", code, common.get("errorMessage"))
            if code in USER_ERRORS:
                raise AppError(common.get("errorMessage") or "검색어를 확인하세요.")
            raise ExternalApiError("주소 검색 서비스가 오류를 돌려줬습니다. 잠시 뒤 다시 시도하세요.")
        return int(common.get("totalCount") or 0), data["results"].get("juso") or []
