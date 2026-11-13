from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd

PROPERTY_RECORDS_TABLE = "property_records"
HISTORICAL_RECORD_KIND = "historical_transaction"
DEMO_RECORD_KIND = "synthetic_demo_listing"
HISTORICAL_SOURCE_TABLE = "secondary_sales"
DEMO_SOURCE_TABLE = "demo_property_listings"
HISTORICAL_SOURCE_FILE = "secondary_sales.csv"
DEMO_SOURCE_FILE = "demo_property_listings.csv"
DEMO_SOURCE_MARKER = "synthetic_demo"

HISTORICAL_COLUMNS = (
    "id",
    "date_listed",
    "community",
    "zone",
    "is_freehold",
    "lat",
    "lon",
    "property_category",
    "property_type",
    "bedrooms",
    "area_sqft",
    "area_m2",
    "floor",
    "total_floors",
    "year_built",
    "view",
    "furnishing",
    "condition",
    "parking_spaces",
    "chiller_included",
    "metro_station",
    "metro_line",
    "metro_distance_min",
    "metro_distance_type",
    "to_burj_khalifa_km",
    "price_usd",
    "price_per_sqft_usd",
    "price_per_m2_usd",
    "mortgage_rate_at_listing",
)

DEMO_COLUMNS = (
    "listing_id",
    "title",
    "listing_type",
    "property_type",
    "community",
    "building_name",
    "bedrooms",
    "bathrooms",
    "area_sqft",
    "price_aed",
    "price_per_sqft_aed",
    "furnishing",
    "view_type",
    "property_condition",
    "availability_status",
    "parking_spaces",
    "amenities",
    "description",
    "currency",
    "source_type",
    "is_synthetic",
    "demo_data_notice",
    "created_date",
)

CANONICAL_COLUMNS = (
    "record_id",
    "source_record_id",
    "source_table",
    "source_file",
    "record_kind",
    "listing_purpose",
    "price_amount",
    "currency",
    "price_period",
    "availability_status",
    "is_synthetic_demo",
    "data_quality_status",
    "record_date",
    "community",
    "zone",
    "normalized_property_type",
    "bedrooms",
    "bathrooms",
    "area",
    "area_sqft",
    "area_m2",
    "furnishing",
    "condition",
    "parking",
    "parking_spaces",
    "view",
    "location",
    "lat",
    "lon",
    "title",
    "building_name",
    "amenities",
    "description",
    "price_per_sqft",
    "price_per_m2",
    "historical_id",
    "historical_date_listed",
    "historical_community",
    "historical_zone",
    "historical_is_freehold",
    "historical_lat",
    "historical_lon",
    "historical_property_category",
    "historical_property_type",
    "historical_bedrooms",
    "historical_area_sqft",
    "historical_area_m2",
    "historical_floor",
    "historical_total_floors",
    "historical_year_built",
    "historical_view",
    "historical_furnishing",
    "historical_condition",
    "historical_parking_spaces",
    "historical_chiller_included",
    "historical_metro_station",
    "historical_metro_line",
    "historical_metro_distance_min",
    "historical_metro_distance_type",
    "historical_to_burj_khalifa_km",
    "historical_price_usd",
    "historical_price_per_sqft_usd",
    "historical_price_per_m2_usd",
    "historical_mortgage_rate_at_listing",
    "demo_listing_id",
    "demo_title",
    "demo_listing_type",
    "demo_property_type",
    "demo_community",
    "demo_building_name",
    "demo_bedrooms",
    "demo_bathrooms",
    "demo_area_sqft",
    "demo_price_aed",
    "demo_price_per_sqft_aed",
    "demo_furnishing",
    "demo_view_type",
    "demo_property_condition",
    "demo_availability_status",
    "demo_parking_spaces",
    "demo_amenities",
    "demo_description",
    "demo_currency",
    "demo_source_type",
    "demo_is_synthetic",
    "demo_data_notice",
    "demo_created_date",
)


def canonical_table_schema_sql() -> str:
    return """
        CREATE TABLE property_records (
            record_id VARCHAR PRIMARY KEY,
            source_record_id VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,
            source_file VARCHAR NOT NULL,
            record_kind VARCHAR NOT NULL,
            listing_purpose VARCHAR NOT NULL,
            price_amount DOUBLE NOT NULL,
            currency VARCHAR NOT NULL,
            price_period VARCHAR NOT NULL,
            availability_status VARCHAR NOT NULL,
            is_synthetic_demo BOOLEAN NOT NULL,
            data_quality_status VARCHAR NOT NULL,
            record_date DATE,
            community VARCHAR,
            zone VARCHAR,
            normalized_property_type VARCHAR,
            bedrooms INTEGER,
            bathrooms INTEGER,
            area DOUBLE,
            area_sqft DOUBLE,
            area_m2 DOUBLE,
            furnishing VARCHAR,
            condition VARCHAR,
            parking INTEGER,
            parking_spaces INTEGER,
            view VARCHAR,
            location VARCHAR,
            lat DOUBLE,
            lon DOUBLE,
            title VARCHAR,
            building_name VARCHAR,
            amenities VARCHAR,
            description VARCHAR,
            price_per_sqft DOUBLE,
            price_per_m2 DOUBLE,
            historical_id VARCHAR,
            historical_date_listed DATE,
            historical_community VARCHAR,
            historical_zone VARCHAR,
            historical_is_freehold BOOLEAN,
            historical_lat DOUBLE,
            historical_lon DOUBLE,
            historical_property_category VARCHAR,
            historical_property_type VARCHAR,
            historical_bedrooms INTEGER,
            historical_area_sqft DOUBLE,
            historical_area_m2 DOUBLE,
            historical_floor DOUBLE,
            historical_total_floors DOUBLE,
            historical_year_built INTEGER,
            historical_view VARCHAR,
            historical_furnishing VARCHAR,
            historical_condition VARCHAR,
            historical_parking_spaces INTEGER,
            historical_chiller_included BOOLEAN,
            historical_metro_station VARCHAR,
            historical_metro_line VARCHAR,
            historical_metro_distance_min INTEGER,
            historical_metro_distance_type VARCHAR,
            historical_to_burj_khalifa_km DOUBLE,
            historical_price_usd DOUBLE,
            historical_price_per_sqft_usd DOUBLE,
            historical_price_per_m2_usd DOUBLE,
            historical_mortgage_rate_at_listing DOUBLE,
            demo_listing_id VARCHAR,
            demo_title VARCHAR,
            demo_listing_type VARCHAR,
            demo_property_type VARCHAR,
            demo_community VARCHAR,
            demo_building_name VARCHAR,
            demo_bedrooms INTEGER,
            demo_bathrooms INTEGER,
            demo_area_sqft DOUBLE,
            demo_price_aed DOUBLE,
            demo_price_per_sqft_aed DOUBLE,
            demo_furnishing VARCHAR,
            demo_view_type VARCHAR,
            demo_property_condition VARCHAR,
            demo_availability_status VARCHAR,
            demo_parking_spaces INTEGER,
            demo_amenities VARCHAR,
            demo_description VARCHAR,
            demo_currency VARCHAR,
            demo_source_type VARCHAR,
            demo_is_synthetic BOOLEAN,
            demo_data_notice VARCHAR,
            demo_created_date DATE
        )
    """


def object_type(connection: duckdb.DuckDBPyConnection, name: str) -> str | None:
    row = connection.execute(
        """
        SELECT table_type
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [name],
    ).fetchone()
    return row[0] if row else None


def object_exists(connection: duckdb.DuckDBPyConnection, name: str) -> bool:
    return object_type(connection, name) is not None


def table_columns(connection: duckdb.DuckDBPyConnection, name: str) -> list[str]:
    return [row[0] for row in connection.execute(f'DESCRIBE "{name}"').fetchall()]


def create_property_records_table(connection: duckdb.DuckDBPyConnection) -> None:
    existing_type = object_type(connection, PROPERTY_RECORDS_TABLE)
    if existing_type == "VIEW":
        raise ValueError("property_records must be a table, not a view")
    if existing_type is None:
        connection.execute(canonical_table_schema_sql())
        return
    if table_columns(connection, PROPERTY_RECORDS_TABLE) != list(CANONICAL_COLUMNS):
        raise ValueError("property_records schema does not match the canonical schema")


def _require_columns(frame: pd.DataFrame, expected: Iterable[str], label: str) -> None:
    missing = sorted(set(expected) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _date_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce").dt.date


def _nullable_series(
    frame: pd.DataFrame,
    column: str,
    *,
    dtype: str | None = None,
) -> pd.Series:
    values = frame[column]
    if dtype:
        values = values.astype(dtype)
    return values


def _empty_source_columns(frame: pd.DataFrame, prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}{column}": pd.Series([None] * len(frame), index=frame.index)
        for column in (HISTORICAL_COLUMNS if prefix == "historical_" else DEMO_COLUMNS)
    }


def canonical_frame_from_historical(frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(frame, HISTORICAL_COLUMNS, "historical source frame")
    source = frame.loc[:, list(HISTORICAL_COLUMNS)].copy()
    source["date_listed"] = _date_series(source, "date_listed")
    source_ids = source["id"].astype("string")

    values: dict[str, Any] = {
        "record_id": "historical:" + source_ids,
        "source_record_id": source["id"],
        "source_table": HISTORICAL_SOURCE_TABLE,
        "source_file": HISTORICAL_SOURCE_FILE,
        "record_kind": HISTORICAL_RECORD_KIND,
        "listing_purpose": "sale",
        "price_amount": source["price_usd"],
        "currency": "USD",
        "price_period": "transaction_price",
        "availability_status": "historical_not_available",
        "is_synthetic_demo": False,
        "data_quality_status": "historical_unverified",
        "record_date": source["date_listed"],
        "community": source["community"],
        "zone": source["zone"],
        "normalized_property_type": source["property_category"],
        "bedrooms": source["bedrooms"],
        "bathrooms": None,
        "area": source["area_sqft"],
        "area_sqft": source["area_sqft"],
        "area_m2": source["area_m2"],
        "furnishing": source["furnishing"],
        "condition": source["condition"],
        "parking": source["parking_spaces"],
        "parking_spaces": source["parking_spaces"],
        "view": source["view"],
        "location": source["community"],
        "lat": source["lat"],
        "lon": source["lon"],
        "title": None,
        "building_name": None,
        "amenities": None,
        "description": None,
        "price_per_sqft": source["price_per_sqft_usd"],
        "price_per_m2": source["price_per_m2_usd"],
        **{f"historical_{column}": source[column] for column in HISTORICAL_COLUMNS},
        **_empty_source_columns(source, "demo_"),
    }
    result = pd.DataFrame(values, columns=CANONICAL_COLUMNS)
    return _coerce_canonical_frame(result)


def canonical_frame_from_demo(frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(frame, DEMO_COLUMNS, "demo source frame")
    source = frame.loc[:, list(DEMO_COLUMNS)].copy()
    source["created_date"] = _date_series(source, "created_date")
    source_ids = source["listing_id"].astype("string")

    values: dict[str, Any] = {
        "record_id": "demo:" + source_ids,
        "source_record_id": source["listing_id"],
        "source_table": DEMO_SOURCE_TABLE,
        "source_file": DEMO_SOURCE_FILE,
        "record_kind": DEMO_RECORD_KIND,
        "listing_purpose": source["listing_type"],
        "price_amount": source["price_aed"],
        "currency": source["currency"],
        "price_period": source["listing_type"].map(
            {"sale": "purchase_price", "rent": "annual_rent"}
        ),
        "availability_status": source["availability_status"],
        "is_synthetic_demo": source["is_synthetic"],
        "data_quality_status": "synthetic_simulated",
        "record_date": source["created_date"],
        "community": source["community"],
        "zone": None,
        "normalized_property_type": source["property_type"],
        "bedrooms": source["bedrooms"],
        "bathrooms": source["bathrooms"],
        "area": source["area_sqft"],
        "area_sqft": source["area_sqft"],
        "area_m2": source["area_sqft"].astype(float) * 0.092903,
        "furnishing": source["furnishing"],
        "condition": source["property_condition"],
        "parking": source["parking_spaces"],
        "parking_spaces": source["parking_spaces"],
        "view": source["view_type"],
        "location": source["community"],
        "lat": None,
        "lon": None,
        "title": source["title"],
        "building_name": source["building_name"],
        "amenities": source["amenities"],
        "description": source["description"],
        "price_per_sqft": source["price_per_sqft_aed"],
        "price_per_m2": source["price_per_sqft_aed"] * 10.7639,
        **_empty_source_columns(source, "historical_"),
        **{f"demo_{column}": source[column] for column in DEMO_COLUMNS},
    }
    result = pd.DataFrame(values, columns=CANONICAL_COLUMNS)
    return _coerce_canonical_frame(result)


def _coerce_canonical_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.loc[:, list(CANONICAL_COLUMNS)].copy()
    date_columns = {
        "record_date",
        "historical_date_listed",
        "demo_created_date",
    }
    integer_columns = {
        "bedrooms",
        "bathrooms",
        "parking",
        "parking_spaces",
        "historical_bedrooms",
        "historical_year_built",
        "historical_parking_spaces",
        "historical_metro_distance_min",
        "demo_bedrooms",
        "demo_bathrooms",
        "demo_parking_spaces",
    }
    numeric_columns = {
        "price_amount",
        "area",
        "area_sqft",
        "area_m2",
        "lat",
        "lon",
        "price_per_sqft",
        "price_per_m2",
        "historical_lat",
        "historical_lon",
        "historical_area_sqft",
        "historical_area_m2",
        "historical_floor",
        "historical_total_floors",
        "historical_to_burj_khalifa_km",
        "historical_price_usd",
        "historical_price_per_sqft_usd",
        "historical_price_per_m2_usd",
        "historical_mortgage_rate_at_listing",
        "demo_area_sqft",
        "demo_price_aed",
        "demo_price_per_sqft_aed",
    }
    for column in date_columns:
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.date
    for column in integer_columns:
        result[column] = (
            pd.to_numeric(result[column], errors="coerce").round().astype("Int64")
        )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def canonical_frame_from_sources(
    historical: pd.DataFrame, demo: pd.DataFrame
) -> pd.DataFrame:
    return pd.concat(
        [canonical_frame_from_historical(historical), canonical_frame_from_demo(demo)],
        ignore_index=True,
    ).loc[:, list(CANONICAL_COLUMNS)]


def _insert_frame(
    connection: duckdb.DuckDBPyConnection,
    frame: pd.DataFrame,
    registration_name: str,
) -> None:
    connection.register(registration_name, frame)
    columns = ", ".join(f'"{column}"' for column in CANONICAL_COLUMNS)
    try:
        connection.execute(
            f"""
            INSERT INTO {PROPERTY_RECORDS_TABLE} ({columns})
            SELECT {columns}
            FROM {registration_name}
            """
        )
    finally:
        connection.unregister(registration_name)


def insert_canonical_frame(
    connection: duckdb.DuckDBPyConnection, frame: pd.DataFrame
) -> None:
    create_property_records_table(connection)
    _insert_frame(connection, frame, "canonical_records_frame")


def compatibility_view_sql(view_name: str) -> str:
    if view_name == HISTORICAL_SOURCE_TABLE:
        return """
            SELECT
                historical_id AS id,
                historical_date_listed AS date_listed,
                historical_community AS community,
                historical_zone AS zone,
                historical_is_freehold AS is_freehold,
                historical_lat AS lat,
                historical_lon AS lon,
                historical_property_category AS property_category,
                historical_property_type AS property_type,
                historical_bedrooms AS bedrooms,
                historical_area_sqft AS area_sqft,
                historical_area_m2 AS area_m2,
                historical_floor AS floor,
                historical_total_floors AS total_floors,
                historical_year_built AS year_built,
                historical_view AS view,
                historical_furnishing AS furnishing,
                historical_condition AS condition,
                historical_parking_spaces AS parking_spaces,
                historical_chiller_included AS chiller_included,
                historical_metro_station AS metro_station,
                historical_metro_line AS metro_line,
                historical_metro_distance_min AS metro_distance_min,
                historical_metro_distance_type AS metro_distance_type,
                historical_to_burj_khalifa_km AS to_burj_khalifa_km,
                historical_price_usd AS price_usd,
                historical_price_per_sqft_usd AS price_per_sqft_usd,
                historical_price_per_m2_usd AS price_per_m2_usd,
                historical_mortgage_rate_at_listing AS mortgage_rate_at_listing
            FROM property_records
            WHERE record_kind = 'historical_transaction'
              AND source_table = 'secondary_sales'
        """
    if view_name == DEMO_SOURCE_TABLE:
        return """
            SELECT
                demo_listing_id AS listing_id,
                demo_title AS title,
                demo_listing_type AS listing_type,
                demo_property_type AS property_type,
                demo_community AS community,
                demo_building_name AS building_name,
                demo_bedrooms AS bedrooms,
                demo_bathrooms AS bathrooms,
                demo_area_sqft::BIGINT AS area_sqft,
                demo_price_aed::BIGINT AS price_aed,
                demo_price_per_sqft_aed AS price_per_sqft_aed,
                demo_furnishing AS furnishing,
                demo_view_type AS view_type,
                demo_property_condition AS property_condition,
                demo_availability_status AS availability_status,
                demo_parking_spaces AS parking_spaces,
                demo_amenities AS amenities,
                demo_description AS description,
                demo_currency AS currency,
                demo_source_type AS source_type,
                demo_is_synthetic AS is_synthetic,
                demo_data_notice AS demo_data_notice,
                demo_created_date AS created_date
            FROM property_records
            WHERE record_kind = 'synthetic_demo_listing'
              AND source_table = 'demo_property_listings'
              AND is_synthetic_demo = TRUE
        """
    raise ValueError(f"unsupported compatibility view: {view_name}")


def create_compatibility_view(
    connection: duckdb.DuckDBPyConnection, view_name: str
) -> None:
    current_type = object_type(connection, view_name)
    if current_type == "BASE TABLE":
        raise ValueError(
            f"cannot create compatibility view {view_name!r} while a table exists"
        )
    if current_type == "VIEW":
        connection.execute(f'DROP VIEW "{view_name}"')
    connection.execute(
        f'CREATE VIEW "{view_name}" AS {compatibility_view_sql(view_name)}'
    )


def create_compatibility_views(connection: duckdb.DuckDBPyConnection) -> None:
    create_compatibility_view(connection, HISTORICAL_SOURCE_TABLE)
    create_compatibility_view(connection, DEMO_SOURCE_TABLE)


def validate_property_records(
    connection: duckdb.DuckDBPyConnection,
    *,
    expected_historical: int | None = None,
    expected_demo: int | None = None,
    expected_demo_sale: int | None = None,
    expected_demo_rent: int | None = None,
) -> dict[str, int]:
    create_property_records_table(connection)
    counts = {
        "total": int(
            connection.execute("SELECT COUNT(*) FROM property_records").fetchone()[0]
        ),
        "historical": int(
            connection.execute(
                """
                SELECT COUNT(*) FROM property_records
                WHERE record_kind = 'historical_transaction'
                """
            ).fetchone()[0]
        ),
        "demo": int(
            connection.execute(
                """
                SELECT COUNT(*) FROM property_records
                WHERE record_kind = 'synthetic_demo_listing'
                """
            ).fetchone()[0]
        ),
        "sale": int(
            connection.execute(
                "SELECT COUNT(*) FROM property_records WHERE listing_purpose = 'sale'"
            ).fetchone()[0]
        ),
        "rent": int(
            connection.execute(
                "SELECT COUNT(*) FROM property_records WHERE listing_purpose = 'rent'"
            ).fetchone()[0]
        ),
    }
    duplicate_record_ids = int(
        connection.execute(
            """
            SELECT COUNT(*) - COUNT(DISTINCT record_id)
            FROM property_records
            """
        ).fetchone()[0]
    )
    if duplicate_record_ids:
        raise ValueError("property_records contains duplicate record_id values")
    if counts["total"] != counts["historical"] + counts["demo"]:
        raise ValueError("property_records contains an unknown record_kind")
    if expected_historical is not None and counts["historical"] != expected_historical:
        raise ValueError(
            f"expected {expected_historical} historical records, got {counts['historical']}"
        )
    if expected_demo is not None and counts["demo"] != expected_demo:
        raise ValueError(f"expected {expected_demo} demo records, got {counts['demo']}")
    if expected_demo_sale is not None:
        actual = connection.execute(
            """
            SELECT COUNT(*) FROM property_records
            WHERE record_kind = 'synthetic_demo_listing'
              AND listing_purpose = 'sale'
            """
        ).fetchone()[0]
        if actual != expected_demo_sale:
            raise ValueError(
                f"expected {expected_demo_sale} demo sale records, got {actual}"
            )
    if expected_demo_rent is not None:
        actual = connection.execute(
            """
            SELECT COUNT(*) FROM property_records
            WHERE record_kind = 'synthetic_demo_listing'
              AND listing_purpose = 'rent'
            """
        ).fetchone()[0]
        if actual != expected_demo_rent:
            raise ValueError(
                f"expected {expected_demo_rent} demo rent records, got {actual}"
            )

    invalid = connection.execute(
        """
        SELECT COUNT(*)
        FROM property_records
        WHERE (record_kind = 'historical_transaction'
               AND (listing_purpose <> 'sale'
                    OR currency <> 'USD'
                    OR price_period <> 'transaction_price'
                    OR availability_status <> 'historical_not_available'
                    OR is_synthetic_demo
                    OR data_quality_status <> 'historical_unverified'))
           OR (record_kind = 'synthetic_demo_listing'
               AND (listing_purpose NOT IN ('sale', 'rent')
                    OR currency <> 'AED'
                    OR is_synthetic_demo IS NOT TRUE
                    OR data_quality_status <> 'synthetic_simulated'
                    OR (listing_purpose = 'sale' AND price_period <> 'purchase_price')
                    OR (listing_purpose = 'rent' AND price_period <> 'annual_rent')))
        """
    ).fetchone()[0]
    if invalid:
        raise ValueError(f"property_records contains {invalid} invalid normalized rows")
    return counts


def demo_frame_from_connection(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    cursor = connection.execute(
        """
        SELECT *
        FROM demo_property_listings
        WHERE source_type = ? AND is_synthetic = TRUE
        ORDER BY listing_id
        """,
        [DEMO_SOURCE_MARKER],
    )
    return pd.DataFrame(
        cursor.fetchall(), columns=[item[0] for item in cursor.description]
    )
