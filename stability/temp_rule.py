"""
팝업·행사 매장 판정 (공통 규칙 5, docs/common-rules.md)

공용 파일 permits_base.csv 를 만드는 단계(competition/permits_prep.py)에서 is_temp 열을 붙일 때,
그리고 안정성 축 build_stability.py 에서 같은 함수를 쓴다. 축마다 판정을 다시 만들지 않는다.

규칙 — 아래 둘 중 하나에 해당하고, 기준일까지 '90일 안에 폐업'했으면 팝업
  ① 상호에 '한시적·임시·팝업·행사' 가 들어감
     (상호만 맞고 오래 영업한 가게 — 예: '대행사식당' 10년 영업 — 는 일반 가게)
  ② 팝업이 몰리는 건물: 기준일 전 3년 동안 인허가 30건 이상이고 그중 절반 이상이 90일 안에 폐업한 지번
     (같은 건물이라도 오래 영업한 입점 매장은 일반 가게)

기준일 처리 (공통 규칙 2)
  - 기준일 뒤에 난 인허가는 판정에도, 다발 건물 계산에도 쓰지 않는다 (과거 기준일로 다시 돌려도 결과가 미래 데이터에 흔들리지 않게)
  - 기준일 뒤에 폐업한 가게는 기준일에는 영업 중이었으므로 '90일 안 폐업'으로 보지 않는다
  - 폐업일이 없는 가게(close_date_missing)는 날짜를 모르므로 팝업으로 판정하지 않는다

지번은 jari/common.py 의 jibun_key() 로 맞춘다 (공통 규칙 8: '106-0' = '106', '0-0' 은 묶지 않음)

pandas 만 쓴다.

사용 예 (공용 파일 열 이름이 기본값)
    from temp_rule import flag_temporary
    df["is_temp"] = flag_temporary(df[["name", "jibun_addr", "permit_date", "close_date", "status"]], "2026-09-30")
"""
import importlib.util
import os

import pandas as pd

NAME_PATTERN = r"한시적|임시|팝업|pop[\s-]?up|행사"
SHORT_DAYS = 90      # '90일 안 폐업'
HOT_MIN = 30         # 다발 건물: 3년 인허가 건수 하한
HOT_SHARE = 0.5      # 다발 건물: 90일 안 폐업 비율 하한
HOT_YEARS = 3        # 다발 건물: 기준일 전 몇 년을 볼지

_JARI_COMMON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jari", "common.py")


def _load_jibun_key():
    """jari/common.py 의 jibun_key 를 파일 경로로 읽는다.
    (이름이 흔한 'common' 모듈을 sys.path 로 찾으면 다른 파일이 잡힐 수 있어서)"""
    if not os.path.exists(_JARI_COMMON):
        raise ImportError(f"jibun_key 가 필요합니다: {os.path.normpath(_JARI_COMMON)} 가 없습니다")
    spec = importlib.util.spec_from_file_location("where_to_open_jari_common", _JARI_COMMON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.jibun_key


jibun_key = _load_jibun_key()


def _to_datetime(s):
    """'2026-09-30', '20260930', '2026-09-30 00:00:00', Timestamp, 빈칸/NaN 모두 처리"""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    digits = s.astype("string").str.replace(r"[^0-9]", "", regex=True).str.slice(0, 8)
    return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")


def temp_detail(df, base_date, *, name="name", addr="jibun_addr", open_col="permit_date",
                close_col="close_date", status="status"):
    """가게마다 판정 근거를 돌려준다 (검토·품질 리포트용).
    열: 지번키, 90일내폐업, 이름해당, 다발건물, is_temp"""
    B = pd.Timestamp(base_date)
    o = _to_datetime(df[open_col])
    c = _to_datetime(df[close_col])

    known = o.notna() & (o <= B)                       # 기준일 뒤 인허가는 판정 대상 아님
    closed = c.notna() & (c <= B)                      # 기준일 뒤 폐업 = 기준일엔 영업 중
    if status in df.columns:                           # 영업 중인데 폐업일이 찍힌 데이터 오류는 폐업으로 보지 않음
        closed &= df[status].astype("string").str.contains("폐업", na=False)
    life = (c - o).dt.days
    short = known & closed & life.between(0, SHORT_DAYS)

    named = df[name].astype("string").str.contains(NAME_PATTERN, case=False, regex=True, na=False)

    key = df[addr].astype("string").fillna("").map(jibun_key)
    recent = known & (o > B - pd.DateOffset(years=HOT_YEARS)) & key.notna()
    stats = pd.DataFrame({"key": key[recent], "short": short[recent]}).groupby("key")["short"].agg(["size", "mean"])
    hot_keys = stats.index[(stats["size"] >= HOT_MIN) & (stats["mean"] >= HOT_SHARE)]
    in_hot = key.isin(hot_keys)

    out = pd.DataFrame({
        "지번키": key,
        "90일내폐업": short,
        "이름해당": named & short,
        "다발건물": in_hot & short,
    }, index=df.index)
    out["is_temp"] = out["이름해당"] | out["다발건물"]
    return out


def flag_temporary(df, base_date, **cols):
    """팝업·행사 매장이면 True 인 bool Series (df 와 같은 index). 열 이름이 다르면 cols 로 넘긴다."""
    return temp_detail(df, base_date, **cols)["is_temp"].astype(bool)
