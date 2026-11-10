from __future__ import annotations

import duckdb
import pytest

from voiceforce_agent.lead_storage import DemoLeadDatabase, LeadStorageError


def _build_database(tmp_path):
    database = tmp_path / "voiceforce.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE demo_property_listings (listing_id VARCHAR)")
        connection.execute("INSERT INTO demo_property_listings VALUES ('DEMO-001')")
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
