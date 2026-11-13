from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from .property_search import (
    normalize_budget,
    normalize_furnishing,
    normalize_integer,
    normalize_property_type,
    normalize_transaction_intent,
)
from .sales_data import default_database_path


class LeadStorageError(RuntimeError):
    """Raised when a demo lead cannot be stored safely."""


def _normalize_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("customer_name must be text")
    normalized = " ".join(value.split())
    if len(normalized) < 2 or len(normalized) > 100:
        raise ValueError("customer_name must be between 2 and 100 characters")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("customer_name contains invalid characters")
    return normalized


def _normalize_phone(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("phone_number must be text")
    raw = value.strip()
    if not raw:
        raise ValueError("phone_number is required")
    if raw.count("+") > 1 or ("+" in raw and not raw.startswith("+")):
        raise ValueError("phone_number is invalid")
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        raise ValueError("phone_number must contain 7 to 15 digits")
    return f"+{digits}" if raw.startswith("+") else digits


class DemoLeadDatabase:
    """Consent-gated DuckDB storage for synthetic demo enquiries."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        configured_path = database_path or default_database_path()
        self.database_path = Path(configured_path).expanduser()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Lead database not found: {self.database_path}")
        return duckdb.connect(str(self.database_path))

    @staticmethod
    def _validate_selected_ids(
        connection: duckdb.DuckDBPyConnection,
        selected_listing_ids: list[str] | None,
    ) -> list[str]:
        if selected_listing_ids is None:
            return []
        if not isinstance(selected_listing_ids, list):
            raise ValueError("selected_listing_ids must be a list")
        if len(selected_listing_ids) > 5:
            raise ValueError("selected_listing_ids cannot contain more than 5 IDs")

        normalized_ids: list[str] = []
        for listing_id in selected_listing_ids:
            if not isinstance(listing_id, str) or not listing_id.strip():
                raise ValueError("selected_listing_ids must contain non-empty text IDs")
            normalized_id = listing_id.strip()
            if normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        if not normalized_ids:
            return []
        placeholders = ", ".join("?" for _ in normalized_ids)
        rows = connection.execute(
            f"""
            SELECT source_record_id
            FROM property_records
            WHERE record_kind = 'synthetic_demo_listing'
              AND source_table = 'demo_property_listings'
              AND is_synthetic_demo = TRUE
              AND source_record_id IN ({placeholders})
            """,
            normalized_ids,
        ).fetchall()
        found_ids = {row[0] for row in rows}
        unknown_ids = sorted(set(normalized_ids) - found_ids)
        if unknown_ids:
            raise ValueError(
                "selected_listing_ids contains unknown demo listing IDs: "
                f"{', '.join(unknown_ids)}"
            )
        return normalized_ids

    @staticmethod
    def _create_table(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_leads (
                lead_id VARCHAR PRIMARY KEY,
                customer_name VARCHAR NOT NULL,
                phone_number VARCHAR NOT NULL,
                transaction_intent VARCHAR NOT NULL,
                preferred_community VARCHAR,
                property_type VARCHAR,
                bedrooms INTEGER,
                minimum_budget_aed DOUBLE,
                maximum_budget_aed DOUBLE,
                furnishing_preference VARCHAR,
                selected_listing_ids VARCHAR NOT NULL,
                customer_consent BOOLEAN NOT NULL,
                created_at TIMESTAMP NOT NULL,
                source VARCHAR NOT NULL
            )
            """
        )

    def capture(
        self,
        *,
        customer_name: str,
        phone_number: str,
        customer_consent: bool,
        confirmed_contact_details: bool,
        transaction_intent: str | None,
        preferred_community: str | None = None,
        property_type: str | None = None,
        bedrooms: int | None = None,
        minimum_budget_aed: float | int | None = None,
        maximum_budget_aed: float | int | None = None,
        furnishing_preference: str | None = None,
        selected_listing_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if customer_consent is not True:
            raise ValueError(
                "customer_consent must be true after the customer explicitly agrees"
            )
        if confirmed_contact_details is not True:
            raise ValueError(
                "confirmed_contact_details must be true after the customer confirms "
                "their name and phone number"
            )

        normalized_name = _normalize_name(customer_name)
        normalized_phone = _normalize_phone(phone_number)
        normalized_intent = normalize_transaction_intent(transaction_intent)
        if normalized_intent is None:
            raise ValueError("transaction_intent is required before saving a lead")
        normalized_community = (
            " ".join(preferred_community.split())
            if preferred_community is not None
            else None
        )
        if normalized_community == "":
            normalized_community = None
        if normalized_community and len(normalized_community) > 120:
            raise ValueError("preferred_community is too long")
        normalized_property_type = normalize_property_type(property_type)
        normalized_bedrooms = normalize_integer(bedrooms, "bedrooms")
        minimum = normalize_budget(minimum_budget_aed, "minimum_budget_aed")
        maximum = normalize_budget(maximum_budget_aed, "maximum_budget_aed")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum_budget_aed cannot exceed maximum_budget_aed")
        normalized_furnishing = normalize_furnishing(
            furnishing_preference, field="furnishing_preference"
        )

        try:
            with self._connect() as connection:
                normalized_ids = self._validate_selected_ids(
                    connection, selected_listing_ids
                )
                selected_ids_json = json.dumps(normalized_ids, separators=(",", ":"))
                self._create_table(connection)

                duplicate = connection.execute(
                    """
                    SELECT lead_id
                    FROM demo_leads
                    WHERE phone_number = ?
                      AND transaction_intent = ?
                      AND selected_listing_ids = ?
                      AND created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    [normalized_phone, normalized_intent, selected_ids_json],
                ).fetchone()
                if duplicate:
                    return {
                        "status": "duplicate",
                        "lead_id": duplicate[0],
                        "message": "A matching demo enquiry was already registered recently.",
                    }

                lead_id = f"LEAD-{uuid.uuid4().hex[:12].upper()}"
                created_at = datetime.now(timezone.utc).replace(tzinfo=None)
                connection.execute(
                    """
                    INSERT INTO demo_leads (
                        lead_id,
                        customer_name,
                        phone_number,
                        transaction_intent,
                        preferred_community,
                        property_type,
                        bedrooms,
                        minimum_budget_aed,
                        maximum_budget_aed,
                        furnishing_preference,
                        selected_listing_ids,
                        customer_consent,
                        created_at,
                        source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        lead_id,
                        normalized_name,
                        normalized_phone,
                        normalized_intent,
                        normalized_community,
                        normalized_property_type,
                        normalized_bedrooms,
                        minimum,
                        maximum,
                        normalized_furnishing,
                        selected_ids_json,
                        True,
                        created_at,
                        "voiceforce_demo",
                    ],
                )
        except (duckdb.Error, OSError) as error:
            raise LeadStorageError(
                "The demo enquiry could not be saved right now."
            ) from error

        return {
            "status": "created",
            "lead_id": lead_id,
            "transaction_intent": normalized_intent,
            "selected_listing_ids": normalized_ids,
            "source": "voiceforce_demo",
        }
