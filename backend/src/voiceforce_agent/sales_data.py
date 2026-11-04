from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = REPOSITORY_ROOT / "backend" / "data" / "voiceforce.duckdb"

DATASET_URL = (
    "https://www.kaggle.com/code/sergionefedov/"
    "dubai-real-estate-full-eda-2020-2026/notebook"
)
DATASET_HANDLE = "sergionefedov/dubai-real-estate-sales-and-rentals-20202026"
DATASET_VERSION = 2
SOURCE_FILE = "secondary_sales.csv"
PRICE_CURRENCY = "USD"
PRICE_CURRENCY_NOTE = (
    "All recorded dataset prices and price-per-area values are in USD; no "
    "currency conversion is performed."
)
DATASET_GENERATION_NOTE = (
    "The source documentation describes these records as generated for analysis."
)
LICENSE_FROM_METADATA = "Apache 2.0"
LICENSE_FROM_DESCRIPTION = "CC0 / Public Domain"
LICENSE_STATUS = (
    "Conflicting statements; commercial-use clearance has not been established."
)

EXPECTED_COLUMNS = (
    "id",
    "date_listed",
    "community",
    "zone",
    "is_freehold",
    "lat",
    "lon",
    "property_category",
    "property_type",
    "bedrooms",
    "area_sqft",
    "area_m2",
    "floor",
    "total_floors",
    "year_built",
    "view",
    "furnishing",
    "condition",
    "parking_spaces",
    "chiller_included",
    "metro_station",
    "metro_line",
    "metro_distance_min",
    "metro_distance_type",
    "to_burj_khalifa_km",
    "price_usd",
    "price_per_sqft_usd",
    "price_per_m2_usd",
    "mortgage_rate_at_listing",
)


def default_database_path() -> Path:
    configured_path = os.getenv("VOICEFORCE_SALES_DB")
    return (
        Path(configured_path).expanduser() if configured_path else DEFAULT_DATABASE_PATH
    )
