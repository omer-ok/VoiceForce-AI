from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from voiceforce_agent.lead_storage import DemoLeadDatabase, LeadStorageError
from voiceforce_agent.property_records import (
    canonical_frame_from_demo,
    create_property_records_table,
    insert_canonical_frame,
)


def _build_database(tmp_path):
    database = tmp_path / "voiceforce.duckdb"
    frame = pd.DataFrame(
        [
            {
                "listing_id": "DEMO-001",
                "title": "Synthetic Apartment",
                "listing_type": "sale",
                "property_type": "Apartment",
                "community": "Dubai Marina",
                "building_name": "Synthetic Residence",
                "bedrooms": 2,
                "bathrooms": 2,
                "area_sqft": 1000,
                "price_aed": 2_000_000,
                "price_per_sqft_aed": 2000.0,
                "furnishing": "furnished",
                "view_type": "community",
                "property_condition": "excellent",
                "availability_status": "simulated_available",
                "parking_spaces": 1,
                "amenities": "Gym",
                "description": "Synthetic demo property.",
                "currency": "AED",
                "source_type": "synthetic_demo",
                "is_synthetic": True,
                "demo_data_notice": "Synthetic demo data only.",
                "created_date": "2025-01-01",
            }
        ]
    )
    with duckdb.connect(str(database)) as connection:
        create_property_records_table(connection)
        insert_canonical_frame(connection, canonical_frame_from_demo(frame))
    return database


def _capture_kwargs() -> dict[str, object]:
    return {
        "customer_name": "Aisha Khan",
        "phone_number": "+971 50 123 4567",
        "customer_consent": True,
        "confirmed_contact_details": True,
        "transaction_intent": "buy",
        "preferred_community": "Dubai Marina",
        "property_type": "apartment",
        "bedrooms": 2,
        "maximum_budget_aed": 2_500_000,
        "furnishing_preference": "furnished",
        "selected_listing_ids": ["DEMO-001"],
    }


def test_successful_lead_creation_stores_only_confirmed_consent_data(tmp_path) -> None:
    database = _build_database(tmp_path)
    result = DemoLeadDatabase(database).capture(**_capture_kwargs())

    assert result["status"] == "created"
    assert result["lead_id"].startswith("LEAD-")
    with duckdb.connect(str(database), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT customer_name, phone_number, transaction_intent,
                   maximum_budget_aed, selected_listing_ids, customer_consent
            FROM demo_leads
            """
        ).fetchone()
    assert row == (
        "Aisha Khan",
        "+971501234567",
        "sale",
        2_500_000.0,
        '["DEMO-001"]',
        True,
    )


def test_missing_consent_does_not_create_lead_table_or_record(tmp_path) -> None:
    database = _build_database(tmp_path)
    values = _capture_kwargs()
    values["customer_consent"] = False

    with pytest.raises(ValueError, match="customer_consent"):
        DemoLeadDatabase(database).capture(**values)

    with duckdb.connect(str(database), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    assert "demo_leads" not in tables


def test_contact_confirmation_and_phone_validation_are_required(tmp_path) -> None:
    database = _build_database(tmp_path)
    values = _capture_kwargs()
    values["confirmed_contact_details"] = False
    with pytest.raises(ValueError, match="confirmed_contact_details"):
        DemoLeadDatabase(database).capture(**values)

    values = _capture_kwargs()
    values["phone_number"] = "not a phone number"
    with pytest.raises(ValueError, match="phone_number"):
        DemoLeadDatabase(database).capture(**values)


def test_duplicate_submission_is_reported_without_another_row(tmp_path) -> None:
    database = _build_database(tmp_path)
    store = DemoLeadDatabase(database)

    first = store.capture(**_capture_kwargs())
    second = store.capture(**_capture_kwargs())

    assert second == {
        "status": "duplicate",
        "lead_id": first["lead_id"],
        "message": "A matching demo enquiry was already registered recently.",
    }
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM demo_leads").fetchone()[0] == 1


def test_database_failure_is_safe(tmp_path) -> None:
    store = DemoLeadDatabase(tmp_path / "missing.duckdb")

    with pytest.raises(LeadStorageError, match="could not be saved"):
        store.capture(**_capture_kwargs())
