from __future__ import annotations

import asyncio
import logging

import duckdb
import pandas as pd
import pytest
from livekit.agents.llm import ToolError

from voiceforce_agent.receptionist import Receptionist
from voiceforce_agent.sales_data import EXPECTED_COLUMNS
from voiceforce_agent.sales_ingestion import ingest_secondary_sales
from voiceforce_agent.sales_queries import HistoricalSalesDatabase


def _row(
    record_id: str,
    community: str,
    zone: str,
    price_usd: int,
    *,
    date_listed: str = "2024-01-15",
    property_type: str = "2BR",
    bedrooms: int = 2,
) -> dict[str, object]:
    row = dict.fromkeys(EXPECTED_COLUMNS)
    row.update(
        {
            "id": record_id,
            "date_listed": date_listed,
            "community": community,
            "zone": zone,
            "is_freehold": True,
            "lat": 25.1,
            "lon": 55.2,
            "property_category": "apartment",
            "property_type": property_type,
            "bedrooms": bedrooms,
            "area_sqft": 1000,
            "area_m2": 92.9,
            "year_built": 2020,
            "view": "community",
            "furnishing": "unfurnished",
            "condition": "vacant_on_transfer",
            "parking_spaces": 1,
            "chiller_included": True,
            "metro_station": "Test Station",
            "metro_line": "Red",
            "metro_distance_min": 10,
            "metro_distance_type": "drive",
            "to_burj_khalifa_km": 5.0,
            "price_usd": price_usd,
            "price_per_sqft_usd": price_usd // 1000,
            "price_per_m2_usd": price_usd // 100,
            "mortgage_rate_at_listing": 4.0,
        }
    )
    return row


def _build_database(tmp_path):
    source = tmp_path / "secondary_sales.csv"
    frame = pd.DataFrame(
        [
            _row("S001", "Dubai Marina", "Dubai Marina", 500_000),
            _row("S001", "Dubai Marina", "Dubai Marina", 500_000),
            _row(
                "S002", "Downtown Dubai", "Downtown", 800_000, date_listed="2025-02-01"
            ),
            _row("S003", "Dubai Marina", "Dubai Marina", -1),
        ]
    )
    frame.to_csv(source, index=False)
    database = tmp_path / "voiceforce.duckdb"
    report = ingest_secondary_sales(source, database)
    return database, report


def test_ingestion_is_transparent_and_queries_are_parameterized(tmp_path) -> None:
    database, report = _build_database(tmp_path)

    assert report.input_rows == 4
    assert report.output_rows == 2
    assert report.exact_duplicate_rows_removed == 1
    assert report.invalid_rows_removed == 1
    assert report.null_counts["floor"] == 2
    assert report.null_counts["total_floors"] == 2

    sales = HistoricalSalesDatabase(database)
    result = sales.search(area="Dubai Marina", bedrooms=2)

    assert result["summary"]["record_count"] == 1
    assert result["summary"]["median_price_usd"] == 500_000.0
    assert result["sample_records"][0]["id"] == "S001"
    assert result["price_currency"] == "USD"
    assert "USD" in result["currency_note"]
    assert (
        "not verified Dubai Land Department transactions" in result["availability_note"]
    )

    insights = sales.market_insights(area="Dubai Marina", granularity="year")
    assert insights["trend"][0]["period"] == "2024-01-01"

    comparison = sales.compare_areas(
        area_a="Dubai Marina",
        area_b="Downtown Dubai",
    )
    assert [item["summary"]["record_count"] for item in comparison["areas"]] == [
        1,
        1,
    ]


def test_query_validation_rejects_invalid_ranges(tmp_path) -> None:
    database, _ = _build_database(tmp_path)
    sales = HistoricalSalesDatabase(database)

    with pytest.raises(ValueError, match="cannot exceed"):
        sales.search(min_price_usd=900_000, max_price_usd=100_000)

    with pytest.raises(ValueError, match="cannot be negative"):
        sales.search(min_price_usd=-1)

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        sales.search(start_date="not-a-date")

    with pytest.raises(ValueError, match="must be month or year"):
        sales.market_insights(area="Dubai Marina", granularity="quarter")


def test_empty_and_unsupported_filters_are_explicit_and_parameterized(tmp_path) -> None:
    database, _ = _build_database(tmp_path)
    sales = HistoricalSalesDatabase(database)

    empty = sales.search(area="No Such Dubai Area")
    assert empty["summary"]["record_count"] == 0
    assert empty["sample_records"] == []

    unsupported = sales.search(property_type="castle")
    assert unsupported["summary"]["record_count"] == 0
    assert unsupported["sample_records"] == []

    injection_like = sales.search(area="Dubai Marina' OR 1=1 --")
    assert injection_like["summary"]["record_count"] == 0


def test_provenance_preserves_unresolved_license_statements(tmp_path) -> None:
    database, _ = _build_database(tmp_path)

    with duckdb.connect(str(database), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT license_from_kaggle_metadata,
                   license_from_dataset_description,
                   license_status
            FROM dataset_provenance
            """
        ).fetchone()

    assert row == (
        "Apache 2.0",
        "CC0 / Public Domain",
        "Conflicting statements; commercial-use clearance has not been established.",
    )


def test_receptionist_registers_historical_sales_tools(tmp_path, monkeypatch) -> None:
    database, _ = _build_database(tmp_path)
    monkeypatch.setenv("VOICEFORCE_SALES_DB", str(database))

    receptionist = Receptionist()
    tool_ids = {tool.id for tool in receptionist.tools}

    assert {
        "search_historical_sales",
        "get_market_insights",
        "compare_areas",
    } <= tool_ids
    assert {"search_demo_properties", "capture_customer_lead"} <= tool_ids
    assert "historical dataset records" in receptionist.instructions
    assert "cannot verify live availability" in receptionist.instructions

    descriptions = {tool.id: tool.info.description for tool in receptionist.tools}
    historical_descriptions = [
        descriptions[tool_id]
        for tool_id in (
            "search_historical_sales",
            "get_market_insights",
            "compare_areas",
        )
    ]
    assert all("USD" in description for description in historical_descriptions)
    assert all(
        "historical" in description.lower() for description in historical_descriptions
    )
    assert all(
        "current" in description.lower() or "live" in description.lower()
        for description in historical_descriptions
    )
    assert "simulated" in descriptions["search_demo_properties"].lower()
    assert "[2, 3]" in descriptions["search_demo_properties"]
    assert "clear_community" in descriptions["search_demo_properties"]
    assert "clear_furnishing" in descriptions["search_demo_properties"]
    assert "consent" in descriptions["capture_customer_lead"].lower()

    result = asyncio.run(
        receptionist._run_sales_tool(
            receptionist.sales_database.search,
            area="Dubai Marina",
        )
    )
    assert result["summary"]["record_count"] == 1


def test_property_tool_separates_technical_errors_from_no_results(caplog) -> None:
    receptionist = Receptionist()

    def failing_operation() -> None:
        raise RuntimeError("secret database connection detail")

    with caplog.at_level(logging.ERROR), pytest.raises(ToolError) as error:
        asyncio.run(receptionist._run_property_tool(failing_operation))

    assert "secret database connection detail" not in str(error.value)
    assert "Demo property search failed" in caplog.text
