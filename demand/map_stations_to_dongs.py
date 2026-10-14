import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Point, shape


DATA_DIR = Path(__file__).resolve().parent
STATION_NAME_ALIASES = {
    "자양(뚝섬한강공원)": "뚝섬유원지",
    "당고개": "불암산",
    "평택지제": "지제",
    "한국항공대": "화전",
}
OUTPUT_COLUMNS = [
    "SUB_STA_NM",
    "matched_station_name",
    "match_method",
    "route_count",
    "longitude",
    "latitude",
    "adm_cd",
    "adm_nm",
    "gu",
    "candidate_adm_cd",
    "mapping_status",
    "mapping_reason",
]
DONG_AREA_COLUMNS = ["adm_cd", "adm_cd8", "stat_cd", "adm_nm", "gu"]


def normalize_station_name(name):
    without_alias = re.sub(r"\([^)]*\)", "", name)
    return re.sub(r"\s+", "", without_alias).strip()


def load_station_master(path):
    with path.open(encoding="utf-8-sig") as source:
        rows = json.load(source)["DATA"]

    by_name = defaultdict(list)
    by_normalized_name = defaultdict(list)
    for row in rows:
        name = row["bldn_nm"].strip()
        by_name[name].append(row)
        by_normalized_name[normalize_station_name(name)].append(row)
    return by_name, by_normalized_name


def load_seoul_dongs(path):
    with path.open(encoding="utf-8") as source:
        feature_collection = json.load(source)

    dongs = []
    for feature in feature_collection["features"]:
        properties = feature["properties"]
        if not properties.get("sidonm", "").startswith("서울"):
            continue
        if not properties.get("adm_cd2"):
            raise ValueError("행정동 경계에 adm_cd2 속성이 없습니다.")
        dongs.append((shape(feature["geometry"]), properties))

    if not dongs:
        raise ValueError("GeoJSON에서 서울 행정동 경계를 찾지 못했습니다.")
    return dongs


def resolve_station(name, by_name, by_normalized_name):
    alias_name = STATION_NAME_ALIASES.get(name)
    if alias_name:
        return by_name.get(alias_name, []), alias_name, "known_rename"

    exact_matches = by_name.get(name, [])
    if exact_matches:
        return exact_matches, name, "exact"

    normalized_matches = by_normalized_name.get(normalize_station_name(name), [])
    matched_names = {row["bldn_nm"].strip() for row in normalized_matches}
    if len(matched_names) == 1:
        matched_name = next(iter(matched_names))
        return normalized_matches, matched_name, "parenthetical_alias"
    if len(matched_names) > 1:
        return [], "", "ambiguous_station_name"
    return [], "", "station_not_found"


def find_dongs(point, dongs):
    return [properties for geometry, properties in dongs if geometry.covers(point)]


def map_station(name, by_name, by_normalized_name, dongs):
    matched_rows, matched_name, match_method = resolve_station(
        name, by_name, by_normalized_name
    )
    points = []
    routes = set()
    for row in matched_rows:
        try:
            longitude = float(row["lot"])
            latitude = float(row["lat"])
        except (KeyError, TypeError, ValueError):
            continue
        points.append((longitude, latitude))
        routes.add(row.get("route", ""))

    result = {column: "" for column in OUTPUT_COLUMNS}
    result.update(
        {
            "SUB_STA_NM": name,
            "matched_station_name": matched_name,
            "match_method": match_method,
            "route_count": len(routes),
        }
    )
    if not points:
        result["mapping_status"] = match_method
        return result

    longitude = statistics.median(point[0] for point in points)
    latitude = statistics.median(point[1] for point in points)
    result["longitude"] = f"{longitude:.6f}"
    result["latitude"] = f"{latitude:.6f}"

    candidate_counts = Counter()
    for point_lon, point_lat in points:
        for properties in find_dongs(Point(point_lon, point_lat), dongs):
            candidate_counts[properties["adm_cd2"]] += 1

    candidate_codes = sorted(candidate_counts)
    result["candidate_adm_cd"] = "|".join(candidate_codes)
    representative_hits = find_dongs(Point(longitude, latitude), dongs)

    if len(representative_hits) > 1:
        result["mapping_status"] = "review_boundary_point"
        return result
    elif representative_hits:
        chosen = representative_hits[0]
        if len(candidate_codes) > 1 or (
            candidate_codes and candidate_codes[0] != chosen["adm_cd2"]
        ):
            result["mapping_status"] = "review_multiple_dongs"
            return result
        result["mapping_status"] = "mapped"
    elif candidate_counts:
        result["mapping_status"] = "review_boundary_conflict"
        return result
    else:
        result["mapping_status"] = "outside_seoul"
        return result

    result.update(
        {
            "adm_cd": chosen["adm_cd2"],
            "adm_nm": chosen["adm_nm"].split()[-1],
            "gu": chosen["sggnm"],
        }
    )
    return result


def build_mapping(station_path, demand_path, dongs):
    by_name, by_normalized_name = load_station_master(station_path)
    with demand_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if "SUB_STA_NM" not in (reader.fieldnames or []):
            raise ValueError("수요 CSV에 SUB_STA_NM 컬럼이 없습니다.")
        station_names = [row["SUB_STA_NM"].strip() for row in reader]

    if len(station_names) != len(set(station_names)):
        raise ValueError("수요 CSV의 역명이 유일하지 않습니다.")
    return [
        map_station(name, by_name, by_normalized_name, dongs)
        for name in station_names
    ]


def apply_overrides(rows, overrides_path, dongs):
    with overrides_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"SUB_STA_NM", "adm_cd", "reason"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "수동 매핑 CSV에는 SUB_STA_NM, adm_cd, reason 컬럼이 필요합니다."
            )
        overrides = list(reader)
        if any(None in override for override in overrides):
            raise ValueError("수동 매핑 CSV 행의 컬럼 수가 헤더와 다릅니다.")

    dongs_by_code = {
        properties["adm_cd2"]: properties for _, properties in dongs
    }
    rows_by_name = {row["SUB_STA_NM"]: row for row in rows}
    seen_names = set()
    applied = 0

    for override in overrides:
        name = override["SUB_STA_NM"].strip()
        code = override["adm_cd"].strip()
        reason = override["reason"].strip()
        if not name or name in seen_names:
            raise ValueError(f"수동 매핑 역명이 비었거나 중복됩니다: {name!r}")
        seen_names.add(name)
        if name not in rows_by_name:
            raise ValueError(f"수요 데이터에 없는 역명입니다: {name}")
        if not reason:
            raise ValueError(f"수동 매핑 사유를 입력하세요: {name}")

        row = rows_by_name[name]
        row["mapping_reason"] = reason
        if not code:
            continue
        if len(code) != 10 or not code.isdigit():
            raise ValueError(f"행정동 코드는 숫자 10자리여야 합니다: {name}={code}")
        properties = dongs_by_code.get(code)
        if properties is None:
            raise ValueError(f"행정동 경계에 없는 코드입니다: {name}={code}")
        row.update(
            {
                "adm_cd": code,
                "adm_nm": properties["adm_nm"].split()[-1],
                "gu": properties["sggnm"],
                "mapping_status": "manual_override",
            }
        )
        applied += 1

    return applied, len(overrides) - applied


def enrich_demand(demand_path, mapping_rows, dong_area_path):
    mapping_by_station = {}
    for row in mapping_rows:
        name = row["SUB_STA_NM"]
        if name in mapping_by_station:
            raise ValueError(f"역 매핑 결과에 중복 역명이 있습니다: {name}")
        mapping_by_station[name] = row

    with dong_area_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not set(DONG_AREA_COLUMNS).issubset(reader.fieldnames or []):
            raise ValueError("dong_area.csv에 필요한 행정동 컬럼이 없습니다.")
        dong_rows = list(reader)

    dongs_by_code = {}
    for row in dong_rows:
        code = row["adm_cd"].strip()
        if not code or code in dongs_by_code:
            raise ValueError(f"dong_area.csv의 행정동 코드가 비었거나 중복됩니다: {code}")
        dongs_by_code[code] = row

    with demand_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        if "SUB_STA_NM" not in fieldnames:
            raise ValueError("수요 CSV에 SUB_STA_NM 컬럼이 없습니다.")
        demand_rows = list(reader)

    station_names = [row["SUB_STA_NM"].strip() for row in demand_rows]
    if len(station_names) != len(set(station_names)):
        raise ValueError("수요 CSV의 역명이 유일하지 않습니다.")
    missing_names = set(station_names) - set(mapping_by_station)
    if missing_names:
        raise ValueError(
            "수요 데이터에 매핑 결과가 없는 역명이 있습니다: "
            + ", ".join(sorted(missing_names))
        )

    output_columns = [
        column
        for column in fieldnames
        if column not in DONG_AREA_COLUMNS and column != "area_km2"
    ]
    station_column_index = output_columns.index("SUB_STA_NM") + 1
    output_columns[station_column_index:station_column_index] = DONG_AREA_COLUMNS
    enriched_rows = []
    mapped_count = 0
    for row, name in zip(demand_rows, station_names):
        code = mapping_by_station[name]["adm_cd"].strip()
        dong = dongs_by_code.get(code) if code else None
        if code and dong is None:
            raise ValueError(f"dong_area.csv에 행정동 코드가 없습니다: {name}={code}")
        if dong:
            mapped_count += 1
        row.update(
            {
                column: dong[column].strip() if dong else ""
                for column in DONG_AREA_COLUMNS
            }
        )
        row.pop("area_km2", None)
        enriched_rows.append(row)

    with demand_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=output_columns)
        writer.writeheader()
        writer.writerows(enriched_rows)

    return mapped_count, len(enriched_rows) - mapped_count


def main():
    parser = argparse.ArgumentParser(
        description="역 좌표를 서울 행정동 경계에 공간 매칭합니다."
    )
    parser.add_argument(
        "--stations",
        type=Path,
        default=DATA_DIR / "data" / "서울시 역사마스터 정보.json",
    )
    parser.add_argument(
        "--dongs",
        type=Path,
        default=DATA_DIR / "data" / "HangJeongDong_ver20260701.geojson",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DATA_DIR / "station_dong_overrides.csv",
    )
    parser.add_argument(
        "--dong-area",
        type=Path,
        default=DATA_DIR / "data" / "dong_area.csv",
    )
    parser.add_argument(
        "--demand",
        type=Path,
        default=DATA_DIR / "subway_demand_202409_202609.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "station_dong_mapping.csv",
    )
    args = parser.parse_args()

    dongs = load_seoul_dongs(args.dongs)
    rows = build_mapping(args.stations, args.demand, dongs)
    applied, pending = apply_overrides(rows, args.overrides, dongs)
    enriched_count, unmapped_count = enrich_demand(
        args.demand, rows, args.dong_area
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    statuses = Counter(row["mapping_status"] for row in rows)
    print(f"매핑 결과: {args.output} ({len(rows)}개 역)")
    print(f"수동 매핑 적용: {applied}; 미결: {pending}")
    print(f"수요 CSV 행정동 정보 추가: {enriched_count}; 미매핑: {unmapped_count}")
    for status, count in sorted(statuses.items()):
        print(f"{status}: {count}")


if __name__ == "__main__":
    main()