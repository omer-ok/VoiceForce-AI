from __future__ import annotations

from voiceforce_agent.state import PropertySalesSessionData


def test_omitted_preferences_are_preserved_and_explicit_scopes_clear() -> None:
    state = PropertySalesSessionData()
    state.update_from_search(
        {
            "transaction_intent": "rent",
            "community": "Business Bay",
            "property_type": "Apartment",
            "bedrooms": 2,
            "furnishing": "furnished",
        },
        ["DEMO-001"],
    )

    state.update_from_search(
        {"max_budget_aed": 100_000},
        ["DEMO-002"],
    )
    assert state.preferred_community == "Business Bay"
    assert state.furnishing_preference == "furnished"
    assert state.bedrooms == 2

    state.update_from_search(
        {
            "community_scope": "anywhere",
            "furnishing_scope": "either",
        },
        [],
    )
    assert state.preferred_community is None
    assert state.furnishing_preference is None
    assert state.maximum_budget_aed == 100_000


def test_bedroom_ranges_are_retained_as_preferences() -> None:
    state = PropertySalesSessionData()

    state.update_from_search(
        {"bedroom_counts": [2, 3]},
        ["DEMO-003"],
    )

    assert state.bedroom_counts == [2, 3]
    assert state.bedrooms is None


def test_explicit_budget_and_property_filters_clear_without_restoring_old_values() -> (
    None
):
    state = PropertySalesSessionData()
    state.update_from_search(
        {
            "transaction_intent": "rent",
            "property_type": "Apartment",
            "bedrooms": 2,
            "max_budget_aed": 100_000,
        },
        ["DEMO-001"],
    )

    state.update_from_search(
        {
            "transaction_intent": "sale",
            "property_type_scope": "any",
            "bedroom_scope": "any",
            "budget_scope": "clear",
        }
    )

    assert state.transaction_intent == "sale"
    assert state.property_type is None
    assert state.bedrooms is None
    assert state.bedroom_counts is None
    assert state.minimum_bedrooms is None
    assert state.maximum_budget_aed is None


def test_minimum_bedrooms_replace_exact_bedroom_preferences() -> None:
    state = PropertySalesSessionData()
    state.update_from_search({"bedrooms": 2}, ["DEMO-001"])
    state.update_from_search({"min_bedrooms": 3})

    assert state.minimum_bedrooms == 3
    assert state.bedrooms is None
    assert state.bedroom_counts is None
