from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_demo_listings import (
    COMMUNITIES,
    DEFAULT_COUNT,
    DEFAULT_LISTING_TYPE_COUNTS,
    DEMO_DATA_NOTICE,
    PROPERTY_TYPES,
    REQUIRED_FIELDS,
    backup_existing_demo_listings,
    generate_listings,
    import_into_duckdb,
    write_csv,
)
from voiceforce_agent.property_records import (
    HISTORICAL_COLUMNS,
    canonical_frame_from_historical,
    create_property_records_table,
    insert_canonical_frame,
)


def _create_existing_database(path) -> None:
    historical = dict.fromkeys(HISTORICAL_COLUMNS)
    historical.update(
        {
            "id": "historical-1",
            "date_listed": "2024-01-01",
            "community": "Dubai Marina",
            "zone": "Dubai Marina",
            "property_category": "apartment",
            "property_type": "2BR",
            "bedrooms": 2,
            "area_sqft": 1000,
            "price_usd": 500_000,
        }
    )
    canonical = canonical_frame_from_historical(pd.DataFrame([historical]))
    with duckdb.connect(str(path)) as connection:
        create_property_records_table(connection)
        insert_canonical_frame(connection, canonical)
        connection.execute("CREATE TABLE dataset_provenance (dataset_handle VARCHAR)")
        connection.execute(
            "INSERT INTO dataset_provenance VALUES ('historical-dataset')"
        )
        connection.execute("CREATE TABLE demo_leads (lead_id VARCHAR)")
        connection.execute("INSERT INTO demo_leads VALUES ('LEAD-EXISTING')")


def test_generation_is_reproducible_and_has_required_coverage() -> None:
    listings_a = generate_listings(count=DEFAULT_COUNT, seed=1234)
    listings_b = generate_listings(count=DEFAULT_COUNT, seed=1234)

    assert listings_a == listings_b
    assert len(listings_a) == DEFAULT_COUNT
    assert len({listing["listing_id"] for listing in listings_a}) == DEFAULT_COUNT
    assert Counter(listing["listing_type"] for listing in listings_a) == Counter(
        DEFAULT_LISTING_TYPE_COUNTS
    )
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
    assert imported_rows == DEFAULT_COUNT
    csv_frame = pd.read_csv(csv_path)
    assert list(csv_frame.columns) == list(REQUIRED_FIELDS)
    assert len(csv_frame) == DEFAULT_COUNT

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM demo_property_listings"
            ).fetchone()[0]
            == DEFAULT_COUNT
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM secondary_sales").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0]
            == 1
        )
        assert connection.execute("SELECT COUNT(*) FROM demo_leads").fetchone()[0] == 1
        schema = connection.execute("DESCRIBE demo_property_listings").fetchall()

    assert [column[0] for column in schema] == list(REQUIRED_FIELDS)
    schema_types = {column[0]: column[1] for column in schema}
    assert schema_types["price_aed"] == "BIGINT"
    assert schema_types["is_synthetic"] == "BOOLEAN"
    assert schema_types["created_date"] == "DATE"


def test_seed_backs_up_and_replaces_only_synthetic_rows(tmp_path) -> None:
    database_path = tmp_path / "voiceforce.duckdb"
    _create_existing_database(database_path)
    import_into_duckdb(generate_listings(count=4, seed=99), database_path)

    backup_path = tmp_path / "backups" / "before-m1.csv"
    assert backup_existing_demo_listings(database_path, backup_path) == backup_path
    assert len(pd.read_csv(backup_path)) == 4

    listings = generate_listings()
    assert import_into_duckdb(listings, database_path) == DEFAULT_COUNT
    assert import_into_duckdb(listings, database_path) == DEFAULT_COUNT

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM demo_property_listings
                WHERE source_type = 'synthetic_demo' AND is_synthetic = TRUE
                """
            ).fetchone()[0]
            == DEFAULT_COUNT
        )
        assert (
            dict(
                connection.execute(
                    """
                SELECT listing_type, COUNT(*)
                FROM demo_property_listings
                GROUP BY listing_type
                ORDER BY listing_type
                """
                ).fetchall()
            )
            == DEFAULT_LISTING_TYPE_COUNTS
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT listing_id) "
                "FROM demo_property_listings"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM secondary_sales").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0]
            == 1
        )
        assert connection.execute("SELECT COUNT(*) FROM demo_leads").fetchone()[0] == 1
