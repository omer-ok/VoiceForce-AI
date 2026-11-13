from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .property_records import (
    DEMO_SOURCE_TABLE,
    HISTORICAL_RECORD_KIND,
    HISTORICAL_SOURCE_TABLE,
    canonical_frame_from_historical,
    create_compatibility_view,
    create_property_records_table,
    insert_canonical_frame,
    object_type,
)
from .sales_data import (
    DATASET_GENERATION_NOTE,
    DATASET_HANDLE,
    DATASET_URL,
    DATASET_VERSION,
    EXPECTED_COLUMNS,
    LICENSE_FROM_DESCRIPTION,
    LICENSE_FROM_METADATA,
    LICENSE_STATUS,
    SOURCE_FILE,
    default_database_path,
)

STRING_COLUMNS = (
    "id",
    "community",
    "zone",
    "property_category",
    "property_type",
    "view",
    "furnishing",
    "condition",
    "metro_station",
    "metro_line",
    "metro_distance_type",
)
NUMERIC_COLUMNS = (
    "lat",
    "lon",
    "bedrooms",
    "area_sqft",
    "area_m2",
    "floor",
    "total_floors",
    "year_built",
    "parking_spaces",
    "metro_distance_min",
    "to_burj_khalifa_km",
    "price_usd",
    "price_per_sqft_usd",
    "price_per_m2_usd",
    "mortgage_rate_at_listing",
)
BOOLEAN_COLUMNS = ("is_freehold", "chiller_included")
REQUIRED_COLUMNS = (
    "id",
    "date_listed",
    "community",
    "property_category",
    "property_type",
    "bedrooms",
    "area_sqft",
    "price_usd",
)


@dataclass(frozen=True)
class IngestionReport:
    source_path: str
    database_path: str
    source_file: str
    source_sha256: str
    source_file_size_bytes: int
    input_rows: int
    output_rows: int
    exact_duplicate_rows_removed: int
    duplicate_ids_removed: int
    invalid_rows_removed: int
    null_counts: dict[str, int]
    date_min: str | None
    date_max: str | None
    ignored_columns: list[str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")

    values = series.astype("string").str.strip().str.lower()
    return values.map(
        {
            "true": True,
            "1": True,
            "yes": True,
            "false": False,
            "0": False,
            "no": False,
        }
    ).astype("boolean")


def _clean_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, int, int, int]:
    for column in STRING_COLUMNS:
        frame[column] = frame[column].astype("string").str.strip()
        frame[column] = frame[column].replace("", pd.NA)

    frame["date_listed"] = pd.to_datetime(frame["date_listed"], errors="coerce")

    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in BOOLEAN_COLUMNS:
        frame[column] = _coerce_boolean(frame[column])

    exact_duplicates = int(frame.duplicated().sum())
    frame = frame.drop_duplicates(keep="first")

    duplicate_ids = int(frame["id"].duplicated().sum())
    frame = frame.drop_duplicates(subset=["id"], keep="first")

    invalid_mask = frame[list(REQUIRED_COLUMNS)].isna().any(axis=1)
    invalid_mask |= frame["price_usd"] <= 0
    invalid_mask |= frame["area_sqft"] <= 0
    invalid_rows = int(invalid_mask.sum())
    frame = frame.loc[~invalid_mask].copy()

    frame["date_listed"] = frame["date_listed"].dt.normalize()
    frame["bedrooms"] = frame["bedrooms"].round().astype("Int64")
    frame["year_built"] = frame["year_built"].round().astype("Int64")
    frame["parking_spaces"] = frame["parking_spaces"].round().astype("Int64")
    frame["metro_distance_min"] = frame["metro_distance_min"].round().astype("Int64")

    return frame, exact_duplicates, duplicate_ids, invalid_rows


def _provenance(
    source_path: Path,
    report: IngestionReport,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dataset_handle": DATASET_HANDLE,
                "dataset_version": DATASET_VERSION,
                "source_url": DATASET_URL,
                "source_file": SOURCE_FILE,
                "license_from_kaggle_metadata": LICENSE_FROM_METADATA,
                "license_from_dataset_description": LICENSE_FROM_DESCRIPTION,
                "license_status": LICENSE_STATUS,
                "license_note": (
                    "Both licence statements are preserved because the source "
                    "contains a conflict. Commercial-use clearance has not been "
                    "established."
                ),
                "generation_note": DATASET_GENERATION_NOTE,
                "source_path": str(source_path),
                "source_sha256": report.source_sha256,
                "source_file_size_bytes": report.source_file_size_bytes,
                "input_rows": report.input_rows,
                "output_rows": report.output_rows,
                "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def ingest_secondary_sales(
    source_path: str | Path,
    database_path: str | Path | None = None,
) -> IngestionReport:
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"CSV file not found: {source}")

    frame = pd.read_csv(source)
    missing_columns = sorted(set(EXPECTED_COLUMNS) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"secondary_sales.csv is missing columns: {missing_columns}")

    ignored_columns = sorted(set(frame.columns) - set(EXPECTED_COLUMNS))
    frame = frame.loc[:, list(EXPECTED_COLUMNS)].copy()
    input_rows = len(frame)
    frame, exact_duplicates, duplicate_ids, invalid_rows = _clean_frame(frame)

    date_min = frame["date_listed"].min()
    date_max = frame["date_listed"].max()
    report = IngestionReport(
        source_path=str(source),
        database_path=str(
            Path(database_path).expanduser().resolve()
            if database_path
            else default_database_path().resolve()
        ),
        source_file=SOURCE_FILE,
        source_sha256=_sha256(source),
        source_file_size_bytes=source.stat().st_size,
        input_rows=input_rows,
        output_rows=len(frame),
        exact_duplicate_rows_removed=exact_duplicates,
        duplicate_ids_removed=duplicate_ids,
        invalid_rows_removed=invalid_rows,
        null_counts={
            column: int(count) for column, count in frame.isna().sum().items() if count
        },
        date_min=date_min.date().isoformat() if pd.notna(date_min) else None,
        date_max=date_max.date().isoformat() if pd.notna(date_max) else None,
        ignored_columns=ignored_columns,
    )

    database = Path(report.database_path)
    database.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(database)) as connection:
        canonical_type = object_type(connection, "property_records")
        historical_type = object_type(connection, HISTORICAL_SOURCE_TABLE)
        if canonical_type is None and historical_type == "BASE TABLE":
            raise ValueError(
                "the database still has legacy source tables; run "
                "migrate_property_records.py before ingesting updates"
            )
        if canonical_type not in {None, "BASE TABLE"}:
            raise ValueError("property_records must be a physical table")
        if historical_type == "BASE TABLE":
            raise ValueError(
                "secondary_sales is still a physical table; migrate it before ingesting"
            )

        canonical = canonical_frame_from_historical(frame)
        connection.execute("BEGIN TRANSACTION")
        try:
            create_property_records_table(connection)
            connection.execute(
                """
                DELETE FROM property_records
                WHERE record_kind = ? AND source_table = ?
                """,
                [HISTORICAL_RECORD_KIND, HISTORICAL_SOURCE_TABLE],
            )
            insert_canonical_frame(connection, canonical)
            connection.register("provenance_frame", _provenance(source, report))
            try:
                connection.execute(
                    """
                    CREATE OR REPLACE TABLE dataset_provenance AS
                    SELECT * FROM provenance_frame
                    """
                )
            finally:
                connection.unregister("provenance_frame")

            for view_name in (HISTORICAL_SOURCE_TABLE, DEMO_SOURCE_TABLE):
                if object_type(connection, view_name) is None:
                    create_compatibility_view(connection, view_name)
                elif object_type(connection, view_name) == "BASE TABLE":
                    raise ValueError(
                        f"{view_name} is still a physical table; migrate it first"
                    )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest secondary_sales.csv into DuckDB."
    )
    parser.add_argument("--input", required=True, help="Path to secondary_sales.csv")
    parser.add_argument(
        "--database",
        default=str(default_database_path()),
        help="Output DuckDB path",
    )
    args = parser.parse_args()
    report = ingest_secondary_sales(args.input, args.database)
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
