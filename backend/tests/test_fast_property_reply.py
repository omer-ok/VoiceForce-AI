from copy import deepcopy

import pytest

from voiceforce_agent.fast_property_reply import render_demo_result


def _result():
    return {
        "status": "matches",
        "filters": {
            "transaction_intent": "rent",
            "currency": "AED",
            "price_basis": "annual_rent",
        },
        "results": [
            {
                "listing_id": "DEMO-1",
                "property_type": "Apartment",
                "community": "Dubai Marina",
                "bedrooms": 2,
                "price_aed": 120000,
                "currency": "AED",
                "price_period": "annual_rent",
                "availability_status": "simulated_available",
            }
        ],
    }


@pytest.mark.parametrize("language", ["en", "ur", "ar"])
def test_only_complete_simulated_aed_results_are_rendered(language):
    reply = render_demo_result(_result(), language)
    assert reply is not None
    assert "120,000" in reply
    assert "Dubai Marina" in reply


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("price_period", "purchase_price"),
        ("availability_status", "available"),
        ("price_aed", None),
        ("bedrooms", None),
        ("listing_id", ""),
    ],
)
def test_untrusted_or_incomplete_result_falls_back(field, value):
    result = deepcopy(_result())
    result["results"][0][field] = value
    assert render_demo_result(result, "en") is None


def test_unapplied_readiness_preference_falls_back():
    result = _result()
    result["filters"]["ready_or_offplan_preference"] = "ready"
    assert render_demo_result(result, "en") is None
