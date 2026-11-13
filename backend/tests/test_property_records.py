from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_demo_listings import generate_listings
from scripts.migrate_property_records import migrate_property_records
from voiceforce_agent.property_records import (
    DEMO_COLUMNS,
    HISTORICAL_COLUMNS,
    canonical_frame_from_demo,
    canonical_frame_from_historical,
)


def _historical_frame(count: int = 50_000) -> pd.DataFrame:
    frame = pd.DataFrame(
        {column: [None] * count for column in HISTORICAL_COLUMNS},
    )
    frame["id"] = [f"S{i:06d}" for i in range(1, count + 1)]
    frame["date_listed"] = pd.date_range("2020-01-01", periods=count, freq="D").date
    frame["community"] = [
        "Dubai Marina" if i % 2 else "Downtown Dubai" for i in range(count)
    ]
    frame["zone"] = frame["community"]
    frame["is_freehold"] = True
    frame["lat"] = 25.1
    frame["lon"] = 55.2
    frame["property_category"] = "apartment"
    frame["property_type"] = "2BR"
    frame["bedrooms"] = 2
    frame["area_sqft"] = 1000.0
    frame["area_m2"] = 92.9
    frame["floor"] = 10.0
    frame["total_floors"] = 30.0
    frame["year_built"] = 2020
    frame["view"] = "community"
    frame["furnishing"] = "unfurnished"
    frame["condition"] = "vacant_on_transfer"
    frame["parking_spaces"] = 1
    frame["chiller_included"] = True
    frame["metro_station"] = "Test Station"
    frame["metro_line"] = "Red"
    frame["metro_distance_min"] = 10
    frame["metro_distance_type"] = "drive"
    frame["to_burj_khalifa_km"] = 5.0
    frame["price_usd"] = [500_000 + index for index in range(count)]
    frame["price_per_sqft_usd"] = frame["price_usd"] / frame["area_sqft"]
    frame["price_per_m2_usd"] = frame["price_usd"] / frame["area_m2"]
    frame["mortgage_rate_at_listing"] = 4.0
    return frame


def _create_legacy_database(path: Path) -> tuple[tuple, tuple]:
    historical = _historical_frame()
    demo = pd.DataFrame(generate_listings())
    demo["created_date"] = pd.to_datetime(demo["created_date"]).dt.date
    provenance = ("historical-dataset", "unchanged")
    lead = ("LEAD-EXISTING", "existing customer")

    with duckdb.connect(str(path)) as connection:
        connection.register("historical_frame", historical)
        connection.execute(
            "CREATE TABLE secondary_sales AS SELECT * FROM historical_frame"
        )
        connection.unregister("historical_frame")
        connection.register("demo_frame", demo.loc[:, list(DEMO_COLUMNS)])
        connection.execute(
            "CREATE TABLE demo_property_listings AS SELECT * FROM demo_frame"
        )
        connection.unregister("demo_frame")
        connection.execute(
            "CREATE TABLE dataset_provenance (dataset_handle VARCHAR, note VARCHAR)"
        )
        connection.execute("INSERT INTO dataset_provenance VALUES (?, ?)", provenance)
        connection.execute("CREATE TABLE demo_leads (lead_id VARCHAR, note VARCHAR)")
        connection.execute("INSERT INTO demo_leads VALUES (?, ?)", lead)

    return provenance, lead


def test_migration_builds_canonical_counts_currency_periods_and_views(tmp_path) -> None:
    database = tmp_path / "voiceforce.duckdb"
    provenance, lead = _create_legacy_database(database)
    backup_directory = tmp_path / "backups"

    result = migrate_property_records(database, backup_directory)

    assert result["migrated"] is True
    assert result["counts"] == {
        "total": 50_500,
        "historical": 50_000,
        "demo": 500,
        "sale": 50_250,
        "rent": 250,
    }
    assert Path(result["backup_paths"]["secondary_sales"]).is_file()
    assert Path(result["backup_paths"]["demo_property_listings"]).is_file()

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT record_id) FROM property_records"
        ).fetchone() == (50_500, 50_500)
        assert connection.execute(
            """
            SELECT record_kind, listing_purpose, currency, price_period, COUNT(*)
            FROM property_records
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 2
            """
        ).fetchall() == [
            ("historical_transaction", "sale", "USD", "transaction_price", 50_000),
            ("synthetic_demo_listing", "rent", "AED", "annual_rent", 250),
            ("synthetic_demo_listing", "sale", "AED", "purchase_price", 250),
        ]
        assert (
            connection.execute(
                """
            SELECT COUNT(*)
            FROM property_records
            WHERE record_kind = 'historical_transaction'
              AND (availability_status <> 'historical_not_available'
                   OR data_quality_status <> 'historical_unverified'
                   OR is_synthetic_demo
                   OR currency <> 'USD')
            """
            ).fetchone()[0]
            == 0
        )
        assert connection.execute(
            """
            SELECT historical_id, historical_price_usd, demo_listing_id, demo_price_aed
            FROM property_records
            WHERE record_id = 'historical:S000001'
            """
        ).fetchone() == ("S000001", 500_000.0, None, None)
        assert (
            connection.execute(
                """
            SELECT demo_listing_id, demo_price_aed, demo_currency
            FROM property_records
            WHERE record_id = 'demo:DEMO-DXB-0001'
            """
            ).fetchone()[0]
            == "DEMO-DXB-0001"
        )

        assert [
            row[0] for row in connection.execute("DESCRIBE secondary_sales").fetchall()
        ] == list(HISTORICAL_COLUMNS)
        assert [
            row[0]
            for row in connection.execute("DESCRIBE demo_property_listings").fetchall()
        ] == list(DEMO_COLUMNS)
        assert (
            connection.execute("SELECT COUNT(*) FROM secondary_sales").fetchone()[0]
            == 50_000
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM demo_property_listings"
            ).fetchone()[0]
            == 500
        )
        assert (
            connection.execute(
                "SELECT AVG(price_usd), MEDIAN(price_usd) FROM secondary_sales"
            ).fetchone()
            == connection.execute(
                """
            SELECT AVG(price_amount), MEDIAN(price_amount)
            FROM property_records
            WHERE record_kind = 'historical_transaction'
            """
            ).fetchone()
        )
        assert (
            connection.execute("SELECT * FROM dataset_provenance").fetchone()
            == provenance
        )
        assert connection.execute("SELECT * FROM demo_leads").fetchone() == lead


def test_migration_is_idempotent_and_does_not_duplicate_records(tmp_path) -> None:
    database = tmp_path / "voiceforce.duckdb"
    _create_legacy_database(database)
    backup_directory = tmp_path / "backups"

    first = migrate_property_records(database, backup_directory)
    second = migrate_property_records(database, backup_directory)

    assert first["migrated"] is True
    assert second["migrated"] is False
    assert second["idempotent"] is True
    with duckdb.connect(str(database), read_only=True) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM property_records").fetchone()[0]
            == 50_500
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT record_id) FROM property_records"
            ).fetchone()[0]
            == 0
        )


def test_canonical_mappings_preserve_source_specific_fields() -> None:
    historical = _historical_frame(1)
    demo = pd.DataFrame(generate_listings(count=2))

    historical_canonical = canonical_frame_from_historical(historical)
    demo_canonical = canonical_frame_from_demo(demo)

    assert historical_canonical.loc[0, "historical_metro_station"] == "Test Station"
    assert historical_canonical.loc[0, "historical_price_usd"] == 500_000
    assert pd.isna(historical_canonical.loc[0, "demo_listing_id"])
    assert demo_canonical["demo_listing_id"].tolist() == [
        "DEMO-DXB-0001",
        "DEMO-DXB-0002",
    ]
    assert demo_canonical["price_period"].tolist() == [
        "purchase_price",
        "annual_rent",
    ]
