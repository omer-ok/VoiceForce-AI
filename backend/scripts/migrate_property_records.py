from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from voiceforce_agent.property_records import (
    CANONICAL_COLUMNS,
    DEMO_COLUMNS,
    DEMO_SOURCE_TABLE,
    HISTORICAL_COLUMNS,
    HISTORICAL_SOURCE_TABLE,
    PROPERTY_RECORDS_TABLE,
    canonical_frame_from_sources,
    create_compatibility_views,
    create_property_records_table,
    object_type,
    table_columns,
    validate_property_records,
)
from voiceforce_agent.sales_data import default_database_path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIRECTORY = (
    BACKEND_ROOT / "data" / "backups" / "property_records.before_migration"
)


def _table_frame(connection: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    cursor = connection.execute(f'SELECT * FROM "{table}"')
    return pd.DataFrame(
        cursor.fetchall(),
        columns=[description[0] for description in cursor.description],
    )


def _snapshot(
    connection: duckdb.DuckDBPyConnection, table: str
) -> tuple[list[tuple[str, str]], list[tuple[Any, ...]]]:
    cursor = connection.execute(f'SELECT * FROM "{table}"')
    schema = [
        (row[0], str(row[1]))
        for row in connection.execute(f'DESCRIBE "{table}"').fetchall()
    ]
    return schema, cursor.fetchall()


def _validate_source_schema(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    expected_columns: tuple[str, ...],
) -> None:
    if object_type(connection, table) != "BASE TABLE":
        raise ValueError(f"{table} must be an existing physical source table")
    actual_columns = table_columns(connection, table)
    if actual_columns != list(expected_columns):
        raise ValueError(
            f"{table} schema does not match the established source schema: "
            f"expected {list(expected_columns)}, got {actual_columns}"
        )


def _validate_sources(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _validate_source_schema(connection, HISTORICAL_SOURCE_TABLE, HISTORICAL_COLUMNS)
    _validate_source_schema(connection, DEMO_SOURCE_TABLE, DEMO_COLUMNS)

    historical = _table_frame(connection, HISTORICAL_SOURCE_TABLE)
    demo = _table_frame(connection, DEMO_SOURCE_TABLE)

    historical_ids = historical["id"].dropna().astype(str)
    demo_ids = demo["listing_id"].dropna().astype(str)
    if len(historical_ids) != len(set(historical_ids)):
        raise ValueError("secondary_sales contains duplicate IDs")
    if len(demo_ids) != len(set(demo_ids)):
        raise ValueError("demo_property_listings contains duplicate listing IDs")
    if set(historical_ids) & set(demo_ids):
        raise ValueError("historical and demo source IDs overlap")
    if historical["id"].isna().any():
        raise ValueError("secondary_sales contains a null ID")
    if demo["listing_id"].isna().any():
        raise ValueError("demo_property_listings contains a null listing ID")

    if len(historical) != 50_000:
        raise ValueError(f"expected 50,000 historical rows, got {len(historical)}")
    if len(demo) != 500:
        raise ValueError(f"expected 500 demo rows, got {len(demo)}")
    if set(demo["listing_type"].dropna()) != {"sale", "rent"}:
        raise ValueError("demo listing purposes must be sale and rent")
    distribution = demo["listing_type"].value_counts().to_dict()
    if distribution != {"sale": 250, "rent": 250}:
        raise ValueError(f"expected 250 sale and 250 rent rows, got {distribution}")
    if set(demo["currency"].dropna()) != {"AED"}:
        raise ValueError("demo listings must use AED")
    if set(demo["source_type"].dropna()) != {"synthetic_demo"}:
        raise ValueError("demo listings are missing the synthetic_demo source marker")
    if not bool(demo["is_synthetic"].all()):
        raise ValueError("all demo listings must be marked synthetic")

    return historical, demo


def _export_source_tables(
    historical: pd.DataFrame,
    demo: pd.DataFrame,
    backup_directory: Path,
) -> dict[str, str]:
    backup_directory.mkdir(parents=True, exist_ok=True)
    paths = {
        HISTORICAL_SOURCE_TABLE: backup_directory / "secondary_sales.csv",
        DEMO_SOURCE_TABLE: backup_directory / "demo_property_listings.csv",
    }
    for path in paths.values():
        if path.exists():
            raise FileExistsError(
                f"refusing to overwrite an existing pre-migration backup: {path}"
            )
    historical.to_csv(paths[HISTORICAL_SOURCE_TABLE], index=False)
    demo.to_csv(paths[DEMO_SOURCE_TABLE], index=False)
    return {table: str(path) for table, path in paths.items()}


def _validate_views(connection: duckdb.DuckDBPyConnection) -> None:
    if object_type(connection, HISTORICAL_SOURCE_TABLE) != "VIEW":
        raise ValueError("secondary_sales compatibility view was not created")
    if object_type(connection, DEMO_SOURCE_TABLE) != "VIEW":
        raise ValueError("demo_property_listings compatibility view was not created")
    if table_columns(connection, HISTORICAL_SOURCE_TABLE) != list(HISTORICAL_COLUMNS):
        raise ValueError("secondary_sales compatibility view changed its column shape")
    if table_columns(connection, DEMO_SOURCE_TABLE) != list(DEMO_COLUMNS):
        raise ValueError(
            "demo_property_listings compatibility view changed its column shape"
        )
    if (
        connection.execute("SELECT COUNT(*) FROM secondary_sales").fetchone()[0]
        != 50_000
    ):
        raise ValueError("secondary_sales compatibility view has the wrong row count")
    if (
        connection.execute("SELECT COUNT(*) FROM demo_property_listings").fetchone()[0]
        != 500
    ):
        raise ValueError(
            "demo_property_listings compatibility view has the wrong row count"
        )


def migrate_property_records(
    database_path: str | Path | None = None,
    backup_directory: str | Path = DEFAULT_BACKUP_DIRECTORY,
) -> dict[str, Any]:
    database = (
        Path(database_path).expanduser().resolve()
        if database_path
        else default_database_path().resolve()
    )
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {database}")

    with duckdb.connect(str(database)) as connection:
        canonical_type = object_type(connection, PROPERTY_RECORDS_TABLE)
        source_types = {
            table: object_type(connection, table)
            for table in (HISTORICAL_SOURCE_TABLE, DEMO_SOURCE_TABLE)
        }
        if canonical_type == "BASE TABLE" and source_types == {
            HISTORICAL_SOURCE_TABLE: "VIEW",
            DEMO_SOURCE_TABLE: "VIEW",
        }:
            counts = validate_property_records(
                connection,
                expected_historical=50_000,
                expected_demo=500,
                expected_demo_sale=250,
                expected_demo_rent=250,
            )
            _validate_views(connection)
            return {
                "database_path": str(database),
                "backup_paths": {},
                "migrated": False,
                "idempotent": True,
                "counts": counts,
            }

        if canonical_type is not None:
            raise ValueError(
                "property_records already exists but the source tables are not both "
                "compatibility views; refusing to guess at a partial migration"
            )
        if any(value != "BASE TABLE" for value in source_types.values()):
            raise ValueError(
                "migration requires physical secondary_sales and "
                "demo_property_listings source tables"
            )

        historical, demo = _validate_sources(connection)
        backup_paths = _export_source_tables(
            historical,
            demo,
            Path(backup_directory).expanduser().resolve(),
        )
        preserved = {
            table: _snapshot(connection, table)
            for table in ("demo_leads", "dataset_provenance")
            if object_type(connection, table) is not None
        }
        canonical = canonical_frame_from_sources(historical, demo)

        connection.execute("BEGIN TRANSACTION")
        try:
            create_property_records_table(connection)
            columns = ", ".join(f'"{column}"' for column in CANONICAL_COLUMNS)
            connection.register("property_records_frame", canonical)
            try:
                connection.execute(
                    f"""
                    INSERT INTO {PROPERTY_RECORDS_TABLE} ({columns})
                    SELECT {columns}
                    FROM property_records_frame
                    """
                )
            finally:
                connection.unregister("property_records_frame")

            counts = validate_property_records(
                connection,
                expected_historical=50_000,
                expected_demo=500,
                expected_demo_sale=250,
                expected_demo_rent=250,
            )
            connection.execute(f'DROP TABLE "{HISTORICAL_SOURCE_TABLE}"')
            connection.execute(f'DROP TABLE "{DEMO_SOURCE_TABLE}"')
            create_compatibility_views(connection)
            _validate_views(connection)

            for table, expected_snapshot in preserved.items():
                if _snapshot(connection, table) != expected_snapshot:
                    raise RuntimeError(
                        f"{table} changed during property-record migration"
                    )

            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    return {
        "database_path": str(database),
        "backup_paths": backup_paths,
        "migrated": True,
        "idempotent": False,
        "counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize historical and synthetic property data into DuckDB."
    )
    parser.add_argument(
        "--database",
        default=str(default_database_path()),
        help="DuckDB database path",
    )
    parser.add_argument(
        "--backup-directory",
        default=str(DEFAULT_BACKUP_DIRECTORY),
        help="Directory for pre-migration source-table CSV exports",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            migrate_property_records(args.database, args.backup_directory),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
