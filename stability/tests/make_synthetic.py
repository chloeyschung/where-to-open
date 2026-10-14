"""테스트용 합성 데이터: 실제 API와 같은 스키마로 raw CSV 생성"""
import sys, random
import geopandas as gpd, pandas as pd
from shapely.geometry import Point
random.seed(7)
bnd, out = sys.argv[1], sys.argv[2]
g = gpd.read_file(bnd); g = g[g.sidonm == "서울특별시"].reset_index(drop=True)
g5174 = g.to_crs("EPSG:5174")
uptae = {"LOCALDATA_072404": ["한식", "중국식", "일식", "경양식", "분식", "호프/통닭", "정종/대포집/소주방", "까페", "외국음식전문점(인도,태국등)", "출장조리"],
         "LOCALDATA_072405": ["커피숍", "과자점", "패스트푸드", "아이스크림", "편의점", "기타 휴게음식점"]}
cols = ["OPNSFTEAMCODE","MGTNO","APVPERMYMD","TRDSTATEGBN","TRDSTATENM","DTLSTATEGBN","DTLSTATENM","DCBYMD","SITETEL","SITEAREA","SITEPOSTNO","SITEWHLADDR","RDNWHLADDR","RDNPOSTNO","BPLCNM","LASTMODTS","UPDATEGBN","UPDATEDT","UPTAENM","X","Y","SNTUPTAENM"]
def rnd_point(poly):
    minx, miny, maxx, maxy = poly.bounds
    while True:
        p = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
        if poly.contains(p): return p
# 집중 테스트용으로 5개 동에 업소를 몰아준다
focus = g5174.sample(5, random_state=1).index.tolist() + list(range(len(g5174)))
for svc, ups in uptae.items():
    rows = []
    for i in range(6000 if svc.endswith("04") else 2500):
        k = focus[i % 5] if i < 4000 else random.choice(focus)
        row = g5174.loc[k]; p = rnd_point(row.geometry)
        od = pd.Timestamp("2008-01-01") + pd.Timedelta(days=random.randint(0, 6800))
        r = random.random()
        if r < 0.45:
            st, cd = "폐업", od + pd.Timedelta(days=random.randint(30, 3000))
            if cd > pd.Timestamp("2026-10-10"): st, cd = "영업/정상", None
        elif r < 0.48: st, cd = "휴업", None
        elif r < 0.50: st, cd = "취소/말소/만료/정지/중지", None
        elif r < 0.51: st, cd = "폐업", None          # 폐업일 결측
        else: st, cd = "영업/정상", None
        rows.append({"OPNSFTEAMCODE": "3000000", "MGTNO": f"{svc}-{i}", "APVPERMYMD": od.strftime("%Y-%m-%d") + "     ",
                     "TRDSTATENM": st, "DCBYMD": cd.strftime("%Y-%m-%d") if cd is not None else "",
                     "SITEWHLADDR": f"서울특별시 {row.sggnm} 가상동 {i}", "RDNWHLADDR": "", "BPLCNM": f"가게{i}",
                     "UPDATEDT": "2026-10-01 00:00:00", "UPTAENM": random.choice(ups), "X": f"{p.x:.6f}  ", "Y": f"{p.y:.6f}"})
    # 중복 관리번호(갱신 전 버전) 하나 추가
    dup = dict(rows[0]); dup["UPDATEDT"] = "2020-01-01 00:00:00"; dup["TRDSTATENM"] = "영업/정상"; rows.append(dup)
    # 좌표 없는 건
    nc = dict(rows[1]); nc["MGTNO"] += "-nocoord"; nc["X"] = ""; nc["Y"] = ""; rows.append(nc)
    pd.DataFrame(rows).reindex(columns=cols).fillna("").to_csv(f"{out}/{svc}.csv", index=False, encoding="utf-8-sig")
print("ok")
