import csv
import argparse
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.database import Base, SessionLocal, engine
from app.models import Site, SiteStore

REPO_DIR = Path(__file__).resolve().parent.parent
# 자리 축 결과(jari/sites.py). 용량이 커서 git에 올리지 않고 드라이브에서 받아 data/seoul/ 에 둔다
SITES_CSV = REPO_DIR / "data" / "seoul" / "sites.csv"
HISTORY_CSV = REPO_DIR / "data" / "seoul" / "site_history.csv"
BATCH_SIZE = 5_000


def optional_float(value: str) -> float | None:
    return float(value) if value.strip() else None


def site_batches():
    with SITES_CSV.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        expected = {
            "site_key", "gu", "adm_cd", "permits_10y", "max_concurrent", "per_slot_10y",
            "closed_10y", "avg_months_closed", "open_now", "open_now_names", "dong_avg_single",
            "dong_avg_per_slot",
        }
        missing = expected - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"sites.csv에 필요한 컬럼이 없습니다: {sorted(missing)}")

        batch: list[dict[str, Any]] = []
        for row in reader:
            batch.append(
                {
                    "site_key": row["site_key"],
                    "gu": row["gu"],
                    "adm_cd": row["adm_cd"] or None,
                    "permits_10y": int(row["permits_10y"]),
                    "max_concurrent": int(row["max_concurrent"]),
                    "per_slot_10y": float(row["per_slot_10y"]),
                    "closed_10y": int(row["closed_10y"]),
                    "avg_months_closed": optional_float(row["avg_months_closed"]),
                    "open_now": int(row["open_now"]),
                    "open_now_names": row["open_now_names"] or None,
                    "dong_avg_single": optional_float(row["dong_avg_single"]),
                    "dong_avg_per_slot": optional_float(row["dong_avg_per_slot"]),
                }
            )
            if len(batch) == BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def history_batches(site_ids: dict[str, int]):
    with HISTORY_CSV.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        expected = {"site_key", "mgtno", "name", "kind", "uptae", "opened", "closed", "months", "merged"}
        missing = expected - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"site_history.csv에 필요한 컬럼이 없습니다: {sorted(missing)}")

        batch: list[dict[str, Any]] = []
        for row in reader:
            site_id = site_ids.get(row["site_key"])
            if site_id is None:
                raise ValueError(f"site_history.csv에 sites.csv와 일치하지 않는 site_key가 있습니다: {row['site_key']}")
            batch.append(
                {
                    "site_id": site_id,
                    "mgt_nos": row["mgtno"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "uptae": row["uptae"] or None,
                    "open_date": date.fromisoformat(row["opened"]),
                    "close_date": date.fromisoformat(row["closed"]) if row["closed"] else None,
                    "months": optional_float(row["months"]),
                    "merged": int(row["merged"]),
                }
            )
            if len(batch) == BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def ensure_site_schema() -> None:
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("site_store", schema="public")}
    constraints = inspect(engine).get_unique_constraints("site_store", schema="public")
    with engine.begin() as connection:
        if "kind" not in columns:
            connection.execute(text("ALTER TABLE public.site_store ADD COLUMN kind VARCHAR(20)"))
            connection.execute(text("ALTER TABLE public.site_store ALTER COLUMN kind SET NOT NULL"))
        if "merged" not in columns:
            connection.execute(text("ALTER TABLE public.site_store ADD COLUMN merged INTEGER NOT NULL DEFAULT 0"))
        if not any(set(item.get("column_names") or []) == {"site_id", "mgt_nos"} for item in constraints):
            connection.execute(
                text(
                    "ALTER TABLE public.site_store ADD CONSTRAINT "
                    "uq_site_store_site_id_mgt_nos UNIQUE (site_id, mgt_nos)"
                )
            )


def load_sites() -> tuple[int, int]:
    ensure_site_schema()
    site_count = 0
    history_count = 0

    for batch in site_batches():
        with SessionLocal.begin() as session:
            result = session.execute(insert(Site).values(batch).on_conflict_do_nothing(index_elements=[Site.site_key]))
            site_count += max(result.rowcount or 0, 0)

    with SessionLocal() as session:
        site_ids = dict(session.execute(select(Site.site_key, Site.id)).all())

    for batch in history_batches(site_ids):
        with SessionLocal.begin() as session:
            result = session.execute(
                insert(SiteStore)
                .values(batch)
                .on_conflict_do_nothing(index_elements=[SiteStore.site_id, SiteStore.mgt_nos])
            )
            history_count += max(result.rowcount or 0, 0)

    with SessionLocal() as session:
        site_count = session.scalar(select(func.count()).select_from(Site)) or 0
        history_count = session.scalar(select(func.count()).select_from(SiteStore)) or 0

    return site_count, history_count


def validate_csvs() -> tuple[int, int]:
    site_ids: dict[str, int] = {}
    site_count = 0
    for batch in site_batches():
        for row in batch:
            site_count += 1
            if row["site_key"] in site_ids:
                raise ValueError(f"sites.csv에 중복 site_key가 있습니다: {row['site_key']}")
            site_ids[row["site_key"]] = site_count

    history_count = sum(len(batch) for batch in history_batches(site_ids))
    return site_count, history_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load generated site CSVs into the configured PostgreSQL database.")
    parser.add_argument("--dry-run", action="store_true", help="validate both CSVs without changing the database")
    args = parser.parse_args()

    sites, history = validate_csvs()
    print(f"validated site={sites:,}, site_history={history:,}")
    if not args.dry_run:
        loaded_sites, loaded_history = load_sites()
        print(f"loaded site={loaded_sites:,}, site_store={loaded_history:,}")
