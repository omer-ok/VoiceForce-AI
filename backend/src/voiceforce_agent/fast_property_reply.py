"""Conservative, grounded spoken summaries for the experimental search path."""

from __future__ import annotations

import math
from typing import Any

_TYPES = {
    "Apartment": ("apartment", "اپارٹمنٹ", "شقة"),
    "Villa": ("villa", "ولا", "فيلا"),
    "Townhouse": ("townhouse", "ٹاؤن ہاؤس", "تاون هاوس"),
    "Penthouse": ("penthouse", "پینٹ ہاؤس", "بنتهاوس"),
    "Studio": ("studio", "اسٹوڈیو", "استوديو"),
}


def render_demo_result(result: dict[str, Any], language: str) -> str | None:
    """Render only complete, explicitly synthetic and currency-consistent results."""
    if language not in {"en", "ur", "ar"} or result.get("status") != "matches":
        return None
    filters = result.get("filters")
    rows = result.get("results")
    if not isinstance(filters, dict) or not isinstance(rows, list) or not rows:
        return None
    if filters.get("ready_or_offplan_preference") not in (None, "any"):
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    intent = filters.get("transaction_intent")
    if intent not in ("sale", "rent"):
        return None
    expected_period = {"sale": "purchase_price", "rent": "annual_rent"}[intent]
    price = row.get("price_aed")
    bedrooms = row.get("bedrooms")
    community = row.get("community")
    type_value = row.get("property_type")
    property_type = _TYPES.get(type_value) if isinstance(type_value, str) else None
    if (
        expected_period is None
        or row.get("price_period") != expected_period
        or filters.get("price_basis") != expected_period
        or row.get("currency") != "AED"
        or filters.get("currency") != "AED"
        or row.get("availability_status")
        not in {"simulated_available", "simulated_on_request"}
        or not isinstance(row.get("listing_id"), str)
        or not row["listing_id"]
        or not isinstance(community, str)
        or not community.strip()
        or property_type is None
        or isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not math.isfinite(price)
        or price <= 0
        or isinstance(bedrooms, bool)
        or not isinstance(bedrooms, int)
        or bedrooms < 0
    ):
        return None
    amount = f"{price:,.0f}" if price == int(price) else f"{price:,.2f}"
    count = result.get("match_count")
    more = isinstance(count, int) and not isinstance(count, bool) and count > 1
    if language == "en":
        period = "annual rent" if intent == "rent" else "purchase price"
        subject = (
            property_type[0]
            if bedrooms == 0
            else f"{bedrooms}-bedroom {property_type[0]}"
        )
        question = (
            "Would you like more options?"
            if more
            else "Would you like to adjust the search?"
        )
        return (
            f"One demo option is a {subject} in {community}, "
            f"with an AED {amount} {period}. Availability is simulated, not verified. "
            f"{question}"
        )
    if language == "ur":
        period = "سالانہ کرایہ" if intent == "rent" else "قیمت خرید"
        subject = (
            property_type[1]
            if bedrooms == 0
            else f"{bedrooms} بیڈ روم کا {property_type[1]}"
        )
        question = (
            "کیا آپ مزید آپشنز چاہیں گے؟"
            if more
            else "کیا آپ تلاش تبدیل کرنا چاہیں گے؟"
        )
        return (
            f"ایک ڈیمو آپشن {community} میں {subject} ہے، "
            f"جس کا {period} {amount} درہم ہے. دستیابی فرضی ہے اور تصدیق شدہ نہیں. "
            f"{question}"
        )
    period = "الإيجار السنوي" if intent == "rent" else "سعر الشراء"
    subject = (
        property_type[2]
        if bedrooms == 0
        else f"{property_type[2]} بعدد {bedrooms} غرف نوم"
    )
    question = "هل تريد خيارات أخرى؟" if more else "هل ترغب في تعديل البحث؟"
    return (
        f"أحد خيارات العرض {subject} في {community}، "
        f"{period} {amount} درهم. التوفر افتراضي وغير مؤكد. {question}"
    )
