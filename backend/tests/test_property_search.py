from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest
from livekit.agents.llm import ToolError

from voiceforce_agent.property_search import DemoPropertyDatabase
from voiceforce_agent.receptionist import Receptionist
from voiceforce_agent.state import PropertySalesSessionData

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


def _listing(
    listing_id: str,
    listing_type: str,
    property_type: str,
    community: str,
    bedrooms: int,
    price_aed: int,
    furnishing: str,
) -> dict[str, object]:
    return {
        "listing_id": listing_id,
        "title": f"Synthetic {property_type}",
        "listing_type": listing_type,
        "property_type": property_type,
        "community": community,
        "building_name": "Synthetic Residence",
        "bedrooms": bedrooms,
        "bathrooms": max(1, bedrooms),
        "area_sqft": 1000,
        "price_aed": price_aed,
        "price_per_sqft_aed": price_aed / 1000,
        "furnishing": furnishing,
        "view_type": "community",
        "property_condition": "excellent",
        "availability_status": "simulated_available",
        "parking_spaces": 1,
        "amenities": "Gym; Pool",
        "description": "Synthetic demo property; availability is simulated.",
        "currency": "AED",
        "source_type": "synthetic_demo",
        "is_synthetic": True,
        "demo_data_notice": "Synthetic demo data only.",
        "created_date": "2025-01-01",
    }


def _build_database(tmp_path):
    database = tmp_path / "voiceforce.duckdb"
    frame = pd.DataFrame(
        [
            _listing(
                "DEMO-001",
                "sale",
                "Apartment",
                "Dubai Marina",
                2,
                2_000_000,
                "furnished",
            ),
            _listing(
                "DEMO-002",
                "sale",
                "Apartment",
                "Downtown Dubai",
                2,
                3_000_000,
                "semi_furnished",
            ),
            _listing(
                "DEMO-003",
                "rent",
                "Apartment",
                "Dubai Marina",
                2,
                120_000,
                "unfurnished",
            ),
            _listing(
                "DEMO-004",
                "sale",
                "Villa",
                "Jumeirah Village Circle",
                3,
                1_800_000,
                "unfurnished",
            ),
            _listing(
                "DEMO-005",
                "sale",
                "Apartment",
                "Business Bay",
                3,
                3_500_000,
                "furnished",
            ),
        ],
        columns=DEMO_COLUMNS,
    )
    frame["created_date"] = pd.to_datetime(frame["created_date"]).dt.date
    with duckdb.connect(str(database)) as connection:
        connection.register("demo_frame", frame)
        connection.execute(
            "CREATE TABLE demo_property_listings AS SELECT * FROM demo_frame"
        )
        connection.unregister("demo_frame")
    return database


def test_search_supports_intent_community_bedrooms_budget_and_currency(
    tmp_path,
) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    sale = search.search(
        transaction_intent="buy",
        community="Dubai Marina",
        bedrooms=2,
        max_budget_aed=2_500_000,
    )
    assert sale["status"] == "matches"
    assert sale["result_count"] == 1
    assert sale["results"][0]["listing_id"] == "DEMO-001"
    assert sale["results"][0]["price_period"] == "purchase_price"
    assert sale["filters"]["currency"] == "AED"
    assert "simulated availability" in sale["search_notes"][0]

    rent = search.search(transaction_intent="rent", property_type="apartment")
    assert rent["result_count"] == 1
    assert rent["results"][0]["price_aed"] == 120_000
    assert rent["results"][0]["price_period"] == "annual_rent"


def test_search_supports_property_type_furnishing_and_no_results(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    matches = search.search(
        transaction_intent="buy",
        community="Jumeirah Village Circle",
        property_type="villa",
        bedrooms=3,
        furnishing="unfurnished",
    )
    assert [listing["listing_id"] for listing in matches["results"]] == ["DEMO-004"]

    empty = search.search(
        transaction_intent="buy",
        community="Dubai Marina",
        property_type="studio",
    )
    assert empty["status"] == "no_results"
    assert empty["results"] == []
    assert any("No synthetic demo properties" in note for note in empty["search_notes"])


def test_search_records_but_does_not_apply_unsupported_readiness(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    result = search.search(
        transaction_intent="buy",
        community="Dubai Marina",
        ready_or_offplan_preference="ready",
    )
    assert result["result_count"] == 1
    assert result["filters"]["ready_or_offplan_preference"] == "ready"
    assert any("not applied" in note for note in result["search_notes"])


def test_search_serializes_date_values_and_complete_result(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    result = search.search(transaction_intent="buy", community="Dubai Marina")

    assert result["results"][0]["created_date"] == "2025-01-01"
    assert DemoPropertyDatabase._value(date(2025, 1, 2)) == "2025-01-02"
    assert (
        DemoPropertyDatabase._value(datetime(2025, 1, 2, 3, 4, 5))
        == "2025-01-02T03:04:05"
    )
    json.dumps(result)


def test_search_supports_exact_and_multiple_bedroom_counts(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    exact = search.search(transaction_intent="buy", bedrooms=2)
    ranged = search.search(transaction_intent="buy", bedrooms=[2, 3], limit=5)

    assert {listing["listing_id"] for listing in exact["results"]} == {
        "DEMO-001",
        "DEMO-002",
    }
    assert {listing["listing_id"] for listing in ranged["results"]} == {
        "DEMO-001",
        "DEMO-002",
        "DEMO-004",
        "DEMO-005",
    }
    assert ranged["filters"]["bedroom_counts"] == [2, 3]


def test_search_clears_community_and_furnishing_filters(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    result = search.search(
        transaction_intent="buy",
        community="anywhere in Dubai",
        furnishing="either",
        limit=5,
    )

    assert result["result_count"] == 4
    assert result["filters"]["community_scope"] == "anywhere"
    assert result["filters"]["furnishing_scope"] == "either"


def test_search_rejects_invalid_filters_and_keeps_values_parameterized(
    tmp_path,
) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    with pytest.raises(ValueError, match="property_type"):
        search.search(transaction_intent="buy", property_type="castle")
    with pytest.raises(ValueError, match="between 1 and 5"):
        search.search(transaction_intent="buy", bedrooms=[])
    with pytest.raises(ValueError, match="cannot exceed"):
        search.search(
            transaction_intent="buy",
            min_budget_aed=3_000_000,
            max_budget_aed=1_000_000,
        )

    injection_like = search.search(
        transaction_intent="buy",
        community="Dubai Marina' OR 1=1 --",
    )
    assert injection_like["results"] == []


def test_search_supports_minimum_bedrooms_and_budget_clear(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    minimum = search.search(transaction_intent="buy", min_bedrooms=3, limit=5)
    assert {listing["listing_id"] for listing in minimum["results"]} == {
        "DEMO-004",
        "DEMO-005",
    }
    assert minimum["filters"]["min_bedrooms"] == 3

    cleared = search.search(
        transaction_intent="buy",
        max_budget_aed=None,
        budget_scope="clear",
        property_type="apartment",
        limit=5,
    )
    assert cleared["match_count"] == 3
    assert "max_budget_aed" not in cleared["filters"]
    assert cleared["filters"]["budget_scope"] == "clear"


def test_community_aliases_and_ambiguous_names_are_explicit(tmp_path) -> None:
    search = DemoPropertyDatabase(_build_database(tmp_path))

    alias = search.search(transaction_intent="buy", community="Marina Dubai")
    assert alias["result_count"] == 1
    assert alias["filters"]["community"] == "Dubai Marina"
    assert alias["filters"]["community_input"] == "Marina Dubai"

    with pytest.raises(ValueError, match="ambiguous"):
        search.search(transaction_intent="buy", community="Jumeirah Lake Village")


def test_inventory_summary_uses_actual_demo_table(tmp_path) -> None:
    summary = DemoPropertyDatabase(_build_database(tmp_path)).inventory_summary()

    assert summary["total_records"] == 5
    assert summary["is_synthetic"] is True
    assert {row["listing_type"] for row in summary["transaction_types"]} == {
        "rent",
        "sale",
    }
    assert {row["community"] for row in summary["communities"]} == {
        "Business Bay",
        "Downtown Dubai",
        "Dubai Marina",
        "Jumeirah Village Circle",
    }


def test_receptionist_keeps_explicit_clears_after_database_failure(tmp_path) -> None:
    receptionist = Receptionist()
    receptionist.property_database = DemoPropertyDatabase(_build_database(tmp_path))
    context = SimpleNamespace(userdata=PropertySalesSessionData())
    tool = Receptionist.search_demo_properties._func

    asyncio.run(
        tool(
            receptionist,
            context,
            transaction_intent="rent",
            property_type="apartment",
            max_budget_aed=100_000,
            budget_scope="set",
        )
    )

    def fail(_request):
        raise RuntimeError("database failure details")

    receptionist.property_database.search_normalized = fail
    with pytest.raises(ToolError) as error:
        asyncio.run(
            tool(
                receptionist,
                context,
                transaction_intent="sale",
                budget_scope="clear",
                clear_community=True,
                clear_property_type=True,
                clear_bedrooms=True,
            )
        )
    assert "database failure details" not in str(error.value)
    assert "adjusting the criteria" in str(error.value)

    assert context.userdata.maximum_budget_aed is None
    assert context.userdata.preferred_community is None
    assert context.userdata.property_type is None
    assert context.userdata.bedrooms is None
