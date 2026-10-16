"""temp_rule.flag_temporary 규칙 테스트 (공통 규칙 5).  실행: python stability/tests/test_temp_rule.py  또는 pytest"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from temp_rule import flag_temporary, temp_detail  # noqa: E402

B = "2026-09-30"
DEPT = "서울특별시 강남구 삼성동 159"          # 팝업 다발 건물
OTHER = "서울특별시 마포구 망원동 329-1 2층"     # 평범한 건물


def row(mgt, name, addr, opened, closed=None, status=None):
    return {"mgt_no": mgt, "name": name, "jibun_addr": addr, "permit_date": opened,
            "close_date": closed or "", "status": status or ("폐업" if closed else "영업/정상")}


def base_rows():
    rows = []
    # 다발 건물: 3년 안 40건 중 30건이 10일 영업 → 다발 건물
    for i in range(30):
        d = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 20)
        rows.append(row(f"pop{i}", f"가게{i}", f"{DEPT} 지하1층", d.strftime("%Y-%m-%d"),
                        (d + pd.Timedelta(days=10)).strftime("%Y-%m-%d")))
    for i in range(10):  # 같은 건물 장기 입점 (일부는 부번 0 표기)
        rows.append(row(f"ten{i}", f"입점{i}", f"{DEPT}-0 (지상1층)" if i % 2 else f"{DEPT} 1층", "2023-11-01"))
    return rows


def run(rows, base=B):
    df = pd.DataFrame(rows).set_index("mgt_no", drop=False)
    cols = ["name", "jibun_addr", "permit_date", "close_date", "status"]
    return flag_temporary(df[cols].copy(), base), temp_detail(df[cols].copy(), base)


def test_hot_building_popups_flagged_tenants_kept():
    r, d = run(base_rows())
    assert r[[f"pop{i}" for i in range(30)]].all()
    assert not r[[f"ten{i}" for i in range(10)]].any(), "장기 입점 매장은 팝업 아님"
    assert d.loc["ten1", "지번키"] == d.loc["ten0", "지번키"] == "강남구 삼성동 159", "'159-0' 은 '159' 와 같은 지번"


def test_name_rule_needs_90_days():
    rows = base_rows() + [
        row("n_long", "대행사식당", OTHER, "2015-03-01", "2025-03-01"),       # 10년 영업 → 일반 가게
        row("n_open", "행사뷔페", OTHER, "2020-01-01"),                       # 영업 중 → 일반 가게
        row("n_short", "떡볶이(한시적)", OTHER, "2026-05-01", "2026-05-20"),  # 19일 → 팝업
        row("n_91", "팝업카페", OTHER, "2026-01-01", "2026-04-02"),           # 91일 → 일반 가게
        row("n_90", "임시매장", OTHER, "2026-01-01", "2026-04-01"),           # 90일 → 팝업
        row("plain_short", "망원분식", OTHER, "2026-05-01", "2026-05-20"),    # 이름 X, 다발 건물 X → 일반
    ]
    r, _ = run(rows)
    assert not r["n_long"] and not r["n_open"] and not r["n_91"] and not r["plain_short"]
    assert r["n_short"] and r["n_90"]


def test_after_base_date_ignored():
    rows = base_rows() + [
        row("after_open", "가게X", f"{DEPT} B1", "2026-10-05", "2026-10-09"),        # 기준일 뒤 인허가 → 판정 안 함
        row("close_after", "팝업Y", OTHER, "2026-09-20", "2026-10-05"),              # 기준일 뒤 폐업 → 기준일엔 영업 중
    ]
    r, _ = run(rows)
    assert not r["after_open"] and not r["close_after"]


def test_future_permits_do_not_make_hot_building():
    # 기준일 전에는 평범했던 건물에 기준일 뒤 팝업이 몰려도 다발 건물이 되지 않아야 함
    addr = "서울특별시 송파구 신천동 29"
    rows = [row(f"old{i}", f"매장{i}", addr, "2025-01-01") for i in range(20)]
    rows += [row(f"fut{i}", f"새가게{i}", addr, f"2026-10-0{1 + i % 9}", "2026-10-10") for i in range(40)]
    rows += [row("old_short", "매장S", addr, "2026-06-01", "2026-06-20")]
    r, _ = run(rows)
    assert not r.any()


def test_missing_close_date_and_bad_dates():
    rows = base_rows() + [
        row("missing", "행사식당", f"{DEPT} 2층", "1995-01-01", None, status="폐업"),   # 폐업일 없음 → 판정 안 함
        row("bad", "팝업", OTHER, "", "2026-01-01"),                                   # 인허가일 없음
        row("neg", "팝업", OTHER, "2026-05-01", "2026-04-01"),                         # 폐업 < 인허가
        row("open_with_close", "팝업", OTHER, "2026-05-01", "2026-05-10", status="영업/정상"),  # 데이터 오류
    ]
    r, _ = run(rows)
    assert not r[["missing", "bad", "neg", "open_with_close"]].any()


def test_input_formats_and_index_preserved():
    rows = base_rows()
    df = pd.DataFrame(rows)
    df.index = df.index * 7 + 3                         # 0..n 이 아닌 index
    df["permit_date"] = df["permit_date"].str.replace("-", "")   # '20240101' 형식
    out = flag_temporary(df[["name", "jibun_addr", "permit_date", "close_date", "status"]], B)
    assert out.index.equals(df.index) and out.dtype == bool and int(out.sum()) == 30
    df2 = pd.DataFrame(rows)
    df2["permit_date"] = pd.to_datetime(df2["permit_date"])       # Timestamp 형식
    assert int(flag_temporary(df2, pd.Timestamp(B)).sum()) == 30


def test_custom_column_names():
    df = pd.DataFrame(base_rows()).rename(columns={"name": "BPLCNM", "jibun_addr": "SITEWHLADDR",
                                                   "permit_date": "인허가일", "close_date": "폐업일", "status": "상태"})
    out = flag_temporary(df, B, name="BPLCNM", addr="SITEWHLADDR", open_col="인허가일", close_col="폐업일", status="상태")
    assert int(out.sum()) == 30


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)}개 통과")
