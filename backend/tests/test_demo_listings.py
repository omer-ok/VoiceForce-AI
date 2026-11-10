from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_demo_listings import (
    COMMUNITIES,
    DEMO_DATA_NOTICE,
    PROPERTY_TYPES,
    REQUIRED_FIELDS,
    generate_listings,
    import_into_duckdb,
    write_csv,
)


def _create_existing_database(path) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE TABLE secondary_sales (id VARCHAR)")
        connection.execute("INSERT INTO secondary_sales VALUES ('historical-1')")
        connection.execute("CREATE TABLE dataset_provenance (dataset_handle VARCHAR)")
        connection.execute(
            "INSERT INTO dataset_provenance VALUES ('historical-dataset')"
        )


def test_generation_is_reproducible_and_has_required_coverage() -> None:
    listings_a = generate_listings(count=100, seed=1234)
    listings_b = generate_listings(count=100, seed=1234)

    assert listings_a == listings_b
    assert len(listings_a) == 100
    assert len({listing["listing_id"] for listing in listings_a}) == 100
    assert {listing["community"] for listing in listings_a} == set(COMMUNITIES)
    assert {listing["property_type"] for listing in listings_a} == set(PROPERTY_TYPES)

    for listing in listings_a:
        assert listing["price_aed"] > 0
        assert listing["area_sqft"] > 0
        assert listing["currency"] == "AED"
        assert listing["is_synthetic"] is True
        assert listing["availability_status"].startswith("simulated_")
        assert listing["demo_data_notice"] == DEMO_DATA_NOTICE
        assert listing["price_per_sqft_aed"] == round(
            listing["price_aed"] / listing["area_sqft"], 2
        )


def test_csv_and_duckdb_import_preserve_historical_tables(tmp_path) -> None:
    listings = generate_listings()
    csv_path = tmp_path / "demo_property_listings.csv"
    database_path = tmp_path / "voiceforce.duckdb"
    _create_existing_database(database_path)

    written_path = write_csv(listings, csv_path)
    imported_rows = import_into_duckdb(listings, database_path)

    assert written_path == csv_path.resolve()
    assert imported_rows == 100
    csv_frame = pd.read_csv(csv_path)
    assert list(csv_frame.columns) == list(REQUIRED_FIELDS)
    assert len(csv_frame) == 100

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM demo_property_listings"
            ).fetchone()[0]
            == 100
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM secondary_sales").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0]
            == 1
        )
        schema = connection.execute("DESCRIBE demo_property_listings").fetchall()

    assert [column[0] for column in schema] == list(REQUIRED_FIELDS)
    schema_types = {column[0]: column[1] for column in schema}
    assert schema_types["price_aed"] == "BIGINT"
    assert schema_types["is_synthetic"] == "BOOLEAN"
    assert schema_types["created_date"] == "DATE"
