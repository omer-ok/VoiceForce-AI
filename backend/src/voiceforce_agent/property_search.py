from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from .sales_data import default_database_path

PROPERTY_TYPE_ALIASES = {
    "apartment": "Apartment",
    "apartments": "Apartment",
    "villa": "Villa",
    "villas": "Villa",
    "townhouse": "Townhouse",
    "townhouses": "Townhouse",
    "penthouse": "Penthouse",
    "penthouses": "Penthouse",
    "studio": "Studio",
    "studios": "Studio",
}
TRANSACTION_INTENT_ALIASES = {
    "buy": "sale",
    "buying": "sale",
    "purchase": "sale",
    "purchasing": "sale",
    "sale": "sale",
    "sell": "sale",
    "rent": "rent",
    "rental": "rent",
    "renting": "rent",
}
FURNISHING_ALIASES = {
    "furnished": "furnished",
    "semi furnished": "semi_furnished",
    "semi-furnished": "semi_furnished",
    "semi_furnished": "semi_furnished",
    "unfurnished": "unfurnished",
}
ANYWHERE_COMMUNITY_ALIASES = {
    "all communities",
    "all dubai",
    "any community",
    "anywhere",
    "anywhere in dubai",
}
COMMUNITY_ALIASES = {
    "jlt": "Jumeirah Lake Towers",
    "dubai hills": "Dubai Hills Estate",
    "marina dubai": "Dubai Marina",
}
AMBIGUOUS_COMMUNITIES = {"jumeirah lake village"}
ANY_FURNISHING_ALIASES = {
    "any",
    "any furnishing",
    "any furnishing preference",
    "either",
}
READINESS_ALIASES = {
    "ready": "ready",
    "ready to move": "ready",
    "ready-to-move": "ready",
    "off plan": "off_plan",
    "off-plan": "off_plan",
    "off_plan": "off_plan",
    "any": "any",
}
_VALID_BUDGET_SCOPES = {"keep", "clear", "set"}


def _text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    if len(normalized) > 120:
        raise ValueError(f"{field} is too long")
    return normalized


def normalize_transaction_intent(value: str | None) -> str | None:
    normalized = _text(value, "transaction_intent")
    if normalized is None:
        return None
    try:
        return TRANSACTION_INTENT_ALIASES[normalized.casefold()]
    except KeyError as error:
        raise ValueError("transaction_intent must be buy or rent") from error


def normalize_property_type(value: str | None) -> str | None:
    normalized = _text(value, "property_type")
    if normalized is None:
        return None
    try:
        return PROPERTY_TYPE_ALIASES[normalized.casefold()]
    except KeyError as error:
        raise ValueError(
            "property_type must be apartment, villa, townhouse, penthouse, or studio"
        ) from error


def normalize_furnishing(value: str | None, field: str = "furnishing") -> str | None:
    normalized = _text(value, field)
    if normalized is None:
        return None
    try:
        return FURNISHING_ALIASES[normalized.casefold()]
    except KeyError as error:
        raise ValueError(
            "furnishing must be furnished, semi_furnished, or unfurnished"
        ) from error


def normalize_bedroom_counts(
    value: int | list[int] | None,
) -> list[int] | None:
    """Normalize an exact bedroom count or a list of acceptable counts."""

    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("bedrooms must be an integer or a list of integers")

    if not values or len(values) > 5:
        raise ValueError("bedrooms must contain between 1 and 5 values")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in values):
        raise ValueError("bedrooms must be an integer or a list of integers")
    if any(not 0 <= item <= 20 for item in values):
        raise ValueError("bedrooms must be an integer from 0 to 20")
    return sorted(set(values))


def normalize_readiness(value: str | None) -> str | None:
    normalized = _text(value, "ready_or_offplan_preference")
    if normalized is None:
        return None
    try:
        return READINESS_ALIASES[normalized.casefold()]
    except KeyError as error:
        raise ValueError(
            "ready_or_offplan_preference must be ready, off_plan, or any"
        ) from error


def normalize_budget(value: float | int | None, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return normalized


def normalize_integer(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 20:
        raise ValueError(f"{field} must be an integer from 0 to 20")
    return value


def normalize_budget_scope(
    value: str | None,
    minimum: float | int | None,
    maximum: float | int | None,
) -> str:
    """Resolve the explicit budget update semantics used by the agent tool."""

    if value is None:
        return "set" if minimum is not None or maximum is not None else "keep"
    if not isinstance(value, str) or value.casefold() not in _VALID_BUDGET_SCOPES:
        raise ValueError("budget_scope must be keep, clear, or set")
    scope = value.casefold()
    if scope == "set" and minimum is None and maximum is None:
        raise ValueError("budget_scope set requires a minimum or maximum budget")
    if scope in {"keep", "clear"} and (minimum is not None or maximum is not None):
        raise ValueError(f"budget_scope {scope} cannot include budget values")
    return scope


def normalize_community(value: str | None) -> tuple[str | None, str | None, bool]:
    """Return canonical community, original expression, and alias status."""

    normalized = _text(value, "community")
    if normalized is None:
        return None, None, False
    folded = normalized.casefold()
    if folded in AMBIGUOUS_COMMUNITIES:
        raise ValueError(
            "community 'Jumeirah Lake Village' is ambiguous; please clarify "
            "whether you mean Jumeirah Lake Towers or another community"
        )
    canonical = COMMUNITY_ALIASES.get(folded, normalized)
    return canonical, normalized, canonical != normalized


@dataclass(frozen=True)
class NormalizedPropertySearch:
    transaction_intent: str
    community: str | None
    community_input: str | None
    community_was_alias: bool
    property_type: str | None
    bedrooms: list[int] | None
    min_bedrooms: int | None
    bathrooms: int | None
    min_budget_aed: float | None
    max_budget_aed: float | None
    budget_scope: str
    furnishing: str | None
    readiness: str | None
    limit: int
    clear_community: bool
    clear_furnishing: bool
    clear_property_type: bool
    clear_bedrooms: bool
    filters: dict[str, Any]


class DemoPropertyDatabase:
    """Read-only, parameterized queries over synthetic demo inventory."""

    _BASE_CLAUSES = (
        "record_kind = 'synthetic_demo_listing'",
        "listing_purpose = ?",
        "currency = 'AED'",
        "source_table = 'demo_property_listings'",
        "is_synthetic_demo = TRUE",
    )

    def __init__(self, database_path: str | Path | None = None) -> None:
        configured_path = database_path or os.getenv("VOICEFORCE_SALES_DB")
        self.database_path = (
            Path(configured_path).expanduser()
            if configured_path
            else default_database_path()
        )

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.database_path.is_file():
            raise FileNotFoundError(
                f"Demo property database not found: {self.database_path}"
            )
        return duckdb.connect(str(self.database_path), read_only=True)

    @staticmethod
    def _value(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if hasattr(value, "item"):
            scalar = value.item()
            if isinstance(scalar, (datetime, date)):
                return scalar.isoformat()
            return scalar
        return value

    def normalize_request(
        self,
        *,
        transaction_intent: str | None,
        community: str | None = None,
        property_type: str | None = None,
        bedrooms: int | list[int] | None = None,
        min_bedrooms: int | None = None,
        bathrooms: int | None = None,
        min_budget_aed: float | int | None = None,
        max_budget_aed: float | int | None = None,
        budget_scope: str | None = None,
        furnishing: str | None = None,
        ready_or_offplan_preference: str | None = None,
        limit: int = 3,
        clear_community: bool = False,
        clear_furnishing: bool = False,
        clear_property_type: bool = False,
        clear_bedrooms: bool = False,
    ) -> NormalizedPropertySearch:
        for name, value in (
            ("clear_community", clear_community),
            ("clear_furnishing", clear_furnishing),
            ("clear_property_type", clear_property_type),
            ("clear_bedrooms", clear_bedrooms),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")

        normalized_intent = normalize_transaction_intent(transaction_intent)
        if normalized_intent is None:
            raise ValueError("transaction_intent is required and must be buy or rent")

        normalized_community, community_input, community_was_alias = (
            normalize_community(community)
        )
        if normalized_community and (
            normalized_community.casefold() in ANYWHERE_COMMUNITY_ALIASES
        ):
            clear_community = True
            normalized_community = None
        if clear_community and normalized_community is not None:
            raise ValueError("clear_community cannot be used with a community")

        normalized_property_type = normalize_property_type(property_type)
        if clear_property_type and normalized_property_type is not None:
            raise ValueError("clear_property_type cannot be used with a property type")

        normalized_bedrooms = normalize_bedroom_counts(bedrooms)
        normalized_min_bedrooms = normalize_integer(min_bedrooms, "min_bedrooms")
        if clear_bedrooms and (
            normalized_bedrooms is not None or normalized_min_bedrooms is not None
        ):
            raise ValueError("clear_bedrooms cannot be used with bedroom values")
        if normalized_bedrooms is not None and normalized_min_bedrooms is not None:
            raise ValueError("use bedrooms or min_bedrooms, not both")

        normalized_bathrooms = normalize_integer(bathrooms, "bathrooms")
        minimum = normalize_budget(min_budget_aed, "min_budget_aed")
        maximum = normalize_budget(max_budget_aed, "max_budget_aed")
        resolved_budget_scope = normalize_budget_scope(budget_scope, minimum, maximum)
        if resolved_budget_scope in {"keep", "clear"}:
            minimum = None
            maximum = None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("min_budget_aed cannot exceed max_budget_aed")

        normalized_furnishing_text = _text(furnishing, "furnishing")
        if normalized_furnishing_text and (
            normalized_furnishing_text.casefold() in ANY_FURNISHING_ALIASES
        ):
            clear_furnishing = True
            normalized_furnishing = None
        else:
            normalized_furnishing = normalize_furnishing(normalized_furnishing_text)
        if clear_furnishing and normalized_furnishing is not None:
            raise ValueError("clear_furnishing cannot be used with furnishing")

        normalized_readiness = normalize_readiness(ready_or_offplan_preference)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
            raise ValueError("limit must be an integer from 1 to 5")

        filters: dict[str, Any] = {
            "transaction_intent": normalized_intent,
            "currency": "AED",
            "price_basis": (
                "purchase_price" if normalized_intent == "sale" else "annual_rent"
            ),
        }
        if normalized_community is not None:
            filters["community"] = normalized_community
            if community_was_alias:
                filters["community_input"] = community_input
        elif clear_community:
            filters["community_scope"] = "anywhere"
        if normalized_property_type is not None:
            filters["property_type"] = normalized_property_type
        elif clear_property_type:
            filters["property_type_scope"] = "any"
        if normalized_bedrooms is not None:
            if len(normalized_bedrooms) == 1:
                filters["bedrooms"] = normalized_bedrooms[0]
            else:
                filters["bedroom_counts"] = normalized_bedrooms
        elif normalized_min_bedrooms is not None:
            filters["min_bedrooms"] = normalized_min_bedrooms
        elif clear_bedrooms:
            filters["bedroom_scope"] = "any"
        if normalized_bathrooms is not None:
            filters["bathrooms"] = normalized_bathrooms
        if minimum is not None:
            filters["min_budget_aed"] = minimum
        if maximum is not None:
            filters["max_budget_aed"] = maximum
        if budget_scope is not None or minimum is not None or maximum is not None:
            filters["budget_scope"] = resolved_budget_scope
        if normalized_furnishing is not None:
            filters["furnishing"] = normalized_furnishing
        elif clear_furnishing:
            filters["furnishing_scope"] = "either"
        if normalized_readiness is not None:
            filters["ready_or_offplan_preference"] = normalized_readiness

        return NormalizedPropertySearch(
            transaction_intent=normalized_intent,
            community=normalized_community,
            community_input=community_input,
            community_was_alias=community_was_alias,
            property_type=normalized_property_type,
            bedrooms=normalized_bedrooms,
            min_bedrooms=normalized_min_bedrooms,
            bathrooms=normalized_bathrooms,
            min_budget_aed=minimum,
            max_budget_aed=maximum,
            budget_scope=resolved_budget_scope,
            furnishing=normalized_furnishing,
            readiness=normalized_readiness,
            limit=limit,
            clear_community=clear_community,
            clear_furnishing=clear_furnishing,
            clear_property_type=clear_property_type,
            clear_bedrooms=clear_bedrooms,
            filters=filters,
        )

    def search(
        self,
        *,
        transaction_intent: str | None,
        community: str | None = None,
        property_type: str | None = None,
        bedrooms: int | list[int] | None = None,
        min_bedrooms: int | None = None,
        bathrooms: int | None = None,
        min_budget_aed: float | int | None = None,
        max_budget_aed: float | int | None = None,
        budget_scope: str | None = None,
        furnishing: str | None = None,
        ready_or_offplan_preference: str | None = None,
        limit: int = 3,
        clear_community: bool = False,
        clear_furnishing: bool = False,
        clear_property_type: bool = False,
        clear_bedrooms: bool = False,
    ) -> dict[str, Any]:
        request = self.normalize_request(
            transaction_intent=transaction_intent,
            community=community,
            property_type=property_type,
            bedrooms=bedrooms,
            min_bedrooms=min_bedrooms,
            bathrooms=bathrooms,
            min_budget_aed=min_budget_aed,
            max_budget_aed=max_budget_aed,
            budget_scope=budget_scope,
            furnishing=furnishing,
            ready_or_offplan_preference=ready_or_offplan_preference,
            limit=limit,
            clear_community=clear_community,
            clear_furnishing=clear_furnishing,
            clear_property_type=clear_property_type,
            clear_bedrooms=clear_bedrooms,
        )
        result, _ = self.search_normalized(request)
        return result

    def search_normalized(
        self, request: NormalizedPropertySearch
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        clauses = list(self._BASE_CLAUSES)
        parameters: list[Any] = [request.transaction_intent]

        if request.community is not None:
            clauses.append("lower(community) = lower(?)")
            parameters.append(request.community)
        if request.property_type is not None:
            clauses.append("lower(normalized_property_type) = lower(?)")
            parameters.append(request.property_type)
        if request.bedrooms is not None:
            if len(request.bedrooms) == 1:
                clauses.append("bedrooms = ?")
                parameters.append(request.bedrooms[0])
            else:
                placeholders = ", ".join("?" for _ in request.bedrooms)
                clauses.append(f"bedrooms IN ({placeholders})")
                parameters.extend(request.bedrooms)
        elif request.min_bedrooms is not None:
            clauses.append("bedrooms >= ?")
            parameters.append(request.min_bedrooms)
        if request.bathrooms is not None:
            clauses.append("bathrooms = ?")
            parameters.append(request.bathrooms)
        if request.min_budget_aed is not None:
            clauses.append("price_amount >= ?")
            parameters.append(request.min_budget_aed)
        if request.max_budget_aed is not None:
            clauses.append("price_amount <= ?")
            parameters.append(request.max_budget_aed)
        if request.furnishing is not None:
            clauses.append("lower(furnishing) = lower(?)")
            parameters.append(request.furnishing)

        columns = (
            "demo_listing_id AS listing_id, demo_title AS title, "
            "demo_property_type AS property_type, demo_community AS community, "
            "demo_bedrooms AS bedrooms, demo_bathrooms AS bathrooms, "
            "demo_area_sqft::BIGINT AS area_sqft, "
            "demo_price_aed::BIGINT AS price_aed, demo_furnishing AS furnishing, "
            "demo_view_type AS view_type, demo_description AS description, "
            "demo_currency AS currency, demo_availability_status AS availability_status, "
            "demo_created_date AS created_date"
        )
        where = " AND ".join(clauses)
        query_started = time.monotonic()
        with self._connect() as connection:
            match_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM property_records WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            cursor = connection.execute(
                f"""
                SELECT {columns}
                FROM property_records
                WHERE {where}
                ORDER BY price_amount ASC, source_record_id
                LIMIT ?
                """,
                [*parameters, request.limit],
            )
            result_columns = [description[0] for description in cursor.description]
            rows = [
                {
                    column: self._value(value)
                    for column, value in zip(result_columns, row, strict=True)
                }
                for row in cursor.fetchall()
            ]
        query_duration = time.monotonic() - query_started

        price_period = request.filters["price_basis"]
        for row in rows:
            row["price_period"] = price_period

        notes = [
            "Results come from synthetic demo inventory with simulated availability."
        ]
        if request.readiness and request.readiness != "any":
            notes.append(
                "The demo inventory has no ready/off-plan field, so that preference "
                "was recorded but not applied to the search."
            )
        if not rows:
            notes.append(
                "No synthetic demo properties matched all supplied filters; the "
                "criteria can be adjusted, but this does not establish live availability."
            )

        result = {
            "status": "matches" if rows else "no_results",
            "result_count": len(rows),
            "match_count": match_count,
            "filters": dict(request.filters),
            "results": rows,
            "search_notes": notes,
        }
        return result, {
            "match_count": match_count,
            "returned_count": len(rows),
            "query_duration_seconds": max(0.0, query_duration),
            "sql_parameter_count": len(parameters) + 1,
        }

    def inventory_summary(self) -> dict[str, Any]:
        """Return concise capabilities and counts from the synthetic inventory."""

        base = (
            "record_kind = 'synthetic_demo_listing' "
            "AND source_table = 'demo_property_listings' "
            "AND currency = 'AED' AND is_synthetic_demo = TRUE"
        )
        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM property_records WHERE {base}"
                ).fetchone()[0]
            )
            transaction_types = [
                {"listing_type": row[0], "count": int(row[1])}
                for row in connection.execute(
                    f"""
                    SELECT listing_purpose, COUNT(*)
                    FROM property_records
                    WHERE {base}
                    GROUP BY listing_purpose
                    ORDER BY listing_purpose
                    """
                ).fetchall()
            ]
            property_types = [
                {"property_type": row[0], "count": int(row[1])}
                for row in connection.execute(
                    f"""
                    SELECT normalized_property_type, COUNT(*)
                    FROM property_records
                    WHERE {base}
                    GROUP BY normalized_property_type
                    ORDER BY normalized_property_type
                    """
                ).fetchall()
            ]
            communities = [
                {"community": row[0], "count": int(row[1])}
                for row in connection.execute(
                    f"""
                    SELECT community, COUNT(*)
                    FROM property_records
                    WHERE {base}
                    GROUP BY community
                    ORDER BY community
                    """
                ).fetchall()
            ]
            bedroom_counts = [
                {"bedrooms": int(row[0]), "count": int(row[1])}
                for row in connection.execute(
                    f"""
                    SELECT bedrooms, COUNT(*)
                    FROM property_records
                    WHERE {base}
                    GROUP BY bedrooms
                    ORDER BY bedrooms
                    """
                ).fetchall()
            ]
            price_ranges = [
                {
                    "listing_type": row[0],
                    "currency": "AED",
                    "record_count": int(row[1]),
                    "minimum_price_aed": self._value(row[2]),
                    "maximum_price_aed": self._value(row[3]),
                }
                for row in connection.execute(
                    f"""
                    SELECT listing_purpose, COUNT(*), MIN(price_amount), MAX(price_amount)
                    FROM property_records
                    WHERE {base}
                    GROUP BY listing_purpose
                    ORDER BY listing_purpose
                    """
                ).fetchall()
            ]
            counts_by_type_and_community = [
                {
                    "listing_type": row[0],
                    "property_type": row[1],
                    "community": row[2],
                    "count": int(row[3]),
                }
                for row in connection.execute(
                    f"""
                    SELECT listing_purpose, normalized_property_type, community, COUNT(*)
                    FROM property_records
                    WHERE {base}
                    GROUP BY listing_purpose, normalized_property_type, community
                    ORDER BY listing_purpose, normalized_property_type, community
                    """
                ).fetchall()
            ]

        return {
            "inventory": "demo_property_listings",
            "source_type": "synthetic_demo",
            "is_synthetic": True,
            "availability_is_simulated": True,
            "currency": "AED",
            "total_records": total,
            "transaction_types": transaction_types,
            "property_types": property_types,
            "communities": communities,
            "bedroom_counts": bedroom_counts,
            "price_ranges": price_ranges,
            "counts_by_type_and_community": counts_by_type_and_community,
            "notes": [
                "This is illustrative synthetic demo inventory, not verified live availability.",
                "Historical transaction records share canonical storage but are excluded from this demo inventory.",
            ],
        }
