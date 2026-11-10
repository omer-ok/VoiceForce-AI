from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PropertySalesSessionData:
    """Structured, per-call preferences shared by the agent's function tools."""

    # Welcome and language-selection lifecycle.  These values are deliberately
    # per-session so a reconnect or duplicate callback cannot replay the
    # deterministic introduction sequence in the same AgentSession.
    welcome_sequence_started: bool = False
    welcome_sequence_completed: bool = False
    selected_language: str | None = None
    active_agent: str = "receptionist"
    selection_attempts: int = 0
    selection_pending: bool = False
    preferred_language: str = "en"
    last_detected_language: str | None = None
    language_confidence: float | None = None
    transaction_intent: str | None = None
    preferred_community: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bedroom_counts: list[int] | None = None
    minimum_bedrooms: int | None = None
    bathrooms: int | None = None
    minimum_budget_aed: float | None = None
    maximum_budget_aed: float | None = None
    currency: str = "AED"
    furnishing_preference: str | None = None
    ready_or_offplan_preference: str | None = None
    selected_listing_ids: list[str] = field(default_factory=list)

    def update_from_search(
        self, filters: dict[str, Any], listing_ids: list[str] | None = None
    ) -> None:
        """Persist the latest validated search preferences for this call."""

        self.transaction_intent = filters.get(
            "transaction_intent", self.transaction_intent
        )
        if filters.get("community_scope") == "anywhere":
            self.preferred_community = None
        elif "community" in filters:
            self.preferred_community = filters["community"]
        if filters.get("property_type_scope") == "any":
            self.property_type = None
        elif "property_type" in filters:
            self.property_type = filters["property_type"]
        if filters.get("bedroom_scope") == "any":
            self.bedroom_counts = None
            self.bedrooms = None
            self.minimum_bedrooms = None
        elif "min_bedrooms" in filters:
            self.minimum_bedrooms = filters["min_bedrooms"]
            self.bedroom_counts = None
            self.bedrooms = None
        elif "bedroom_counts" in filters:
            self.bedroom_counts = list(filters["bedroom_counts"])
            self.bedrooms = (
                self.bedroom_counts[0] if len(self.bedroom_counts) == 1 else None
            )
            self.minimum_bedrooms = None
        elif "bedrooms" in filters:
            self.bedrooms = filters["bedrooms"]
            self.bedroom_counts = [self.bedrooms]
            self.minimum_bedrooms = None
        self.bathrooms = filters.get("bathrooms", self.bathrooms)
        budget_scope = filters.get("budget_scope")
        if budget_scope == "clear":
            self.minimum_budget_aed = None
            self.maximum_budget_aed = None
        elif budget_scope == "set":
            self.minimum_budget_aed = filters.get("min_budget_aed")
            self.maximum_budget_aed = filters.get("max_budget_aed")
        elif budget_scope != "keep":
            self.minimum_budget_aed = filters.get(
                "min_budget_aed", self.minimum_budget_aed
            )
            self.maximum_budget_aed = filters.get(
                "max_budget_aed", self.maximum_budget_aed
            )
        if filters.get("furnishing_scope") == "either":
            self.furnishing_preference = None
        elif "furnishing" in filters:
            self.furnishing_preference = filters["furnishing"]
        self.ready_or_offplan_preference = filters.get(
            "ready_or_offplan_preference", self.ready_or_offplan_preference
        )
        if listing_ids is not None:
            self.selected_listing_ids = listing_ids
