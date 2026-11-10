from __future__ import annotations

import argparse
import json
import math
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from voiceforce_agent.sales_data import default_database_path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = BACKEND_ROOT / "data" / "demo_property_listings.csv"
DEFAULT_SEED = 20251105
DEFAULT_COUNT = 100

COMMUNITIES = (
    "Dubai Marina",
    "Downtown Dubai",
    "Business Bay",
    "Jumeirah Village Circle",
    "Jumeirah Lake Towers",
    "Dubai Hills Estate",
    "Arabian Ranches",
    "Palm Jumeirah",
    "Dubai Creek Harbour",
    "Al Furjan",
    "Arjan",
    "Dubai Sports City",
    "Dubai Silicon Oasis",
    "Town Square",
    "Jumeirah Village Triangle",
)
PROPERTY_TYPES = ("Apartment", "Villa", "Townhouse", "Penthouse", "Studio")
LISTING_TYPES = ("sale", "rent")
FURNISHING_OPTIONS = ("furnished", "semi_furnished", "unfurnished")
CONDITION_OPTIONS = ("new", "excellent", "good", "renovated")
COMMON_AMENITIES = (
    "Gym",
    "Swimming pool",
    "24/7 security",
    "Covered parking",
    "Residents lounge",
    "Children's play area",
    "Concierge",
    "Landscaped gardens",
)
DEMO_DATA_NOTICE = (
    "Synthetic demo data only: this is not a genuine listing and availability "
    "is simulated; it is not verified property inventory."
)

COMMUNITY_PROFILES = {
    "Dubai Marina": (1.18, ("marina", "city skyline", "waterfront")),
    "Downtown Dubai": (
        1.30,
        ("city skyline", "Burj Khalifa-inspired skyline", "boulevard"),
    ),
    "Business Bay": (1.08, ("canal", "city skyline", "community")),
    "Jumeirah Village Circle": (0.72, ("community", "pool", "park")),
    "Jumeirah Lake Towers": (0.88, ("lake", "city skyline", "community")),
    "Dubai Hills Estate": (1.05, ("golf course", "park", "community")),
    "Arabian Ranches": (1.14, ("golf course", "garden", "community")),
    "Palm Jumeirah": (1.55, ("sea", "marina", "pool")),
    "Dubai Creek Harbour": (1.02, ("creek", "waterfront", "city skyline")),
    "Al Furjan": (0.68, ("community", "garden", "street")),
    "Arjan": (0.64, ("park", "community", "city skyline")),
    "Dubai Sports City": (0.60, ("sports field", "golf course", "community")),
    "Dubai Silicon Oasis": (0.56, ("community", "park", "city skyline")),
    "Town Square": (0.62, ("park", "community", "garden")),
    "Jumeirah Village Triangle": (0.70, ("garden", "community", "park")),
}

TYPE_PROFILES = {
    "Studio": {
        "area": (350, 650),
        "bedrooms": (0, 0),
        "bathrooms": (1, 1),
        "sale_ppsf": (1050, 1550),
    },
    "Apartment": {
        "area": (650, 2200),
        "bedrooms": (1, 3),
        "bathrooms": (1, 4),
        "sale_ppsf": (1100, 1900),
    },
    "Townhouse": {
        "area": (1800, 3600),
        "bedrooms": (2, 4),
        "bathrooms": (3, 5),
        "sale_ppsf": (850, 1350),
    },
    "Villa": {
        "area": (2800, 7500),
        "bedrooms": (3, 6),
        "bathrooms": (4, 7),
        "sale_ppsf": (900, 1700),
    },
    "Penthouse": {
        "area": (1800, 5200),
        "bedrooms": (3, 5),
        "bathrooms": (3, 6),
        "sale_ppsf": (1800, 3000),
    },
}

REQUIRED_FIELDS = (
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


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _rounded_price(value: float, step: int) -> int:
    return max(step, int(round(value / step) * step))


def _generate_price(
    rng: random.Random,
    listing_type: str,
    area_sqft: int,
    property_type: str,
    community_factor: float,
) -> int:
    profile = TYPE_PROFILES[property_type]
    ppsf_low, ppsf_high = profile["sale_ppsf"]
    simulated_sale_price = (
        area_sqft
        * rng.uniform(ppsf_low, ppsf_high)
        * community_factor
        * rng.uniform(0.9, 1.1)
    )
    if listing_type == "sale":
        return _rounded_price(simulated_sale_price, 1_000)

    annual_rent = simulated_sale_price * rng.uniform(0.045, 0.075)
    return _rounded_price(annual_rent, 500)


def _generate_record(rng: random.Random, index: int) -> dict[str, Any]:
    community = COMMUNITIES[index % len(COMMUNITIES)]
    property_type = PROPERTY_TYPES[index % len(PROPERTY_TYPES)]
    listing_type = LISTING_TYPES[index % len(LISTING_TYPES)]
    community_factor, views = COMMUNITY_PROFILES[community]
    profile = TYPE_PROFILES[property_type]

    area_sqft = rng.randint(*profile["area"])
    bedroom_low, bedroom_high = profile["bedrooms"]
    bedrooms = rng.randint(bedroom_low, bedroom_high)
    bathroom_low, bathroom_high = profile["bathrooms"]
    bathrooms = rng.randint(bathroom_low, bathroom_high)
    price_aed = _generate_price(
        rng,
        listing_type,
        area_sqft,
        property_type,
        community_factor,
    )
    price_per_sqft_aed = round(price_aed / area_sqft, 2)
    furnishing = rng.choice(FURNISHING_OPTIONS)
    view_type = rng.choice(views)
    condition = rng.choice(CONDITION_OPTIONS)
    parking_spaces = rng.randint(0 if property_type == "Studio" else 1, 3)
    amenities = "; ".join(rng.sample(COMMON_AMENITIES, rng.randint(3, 5)))
    listing_id = f"DEMO-DXB-{index + 1:04d}"
    created_date = date(2025, 1, 1) + timedelta(days=rng.randint(0, 364))
    bedroom_label = "Studio" if bedrooms == 0 else f"{bedrooms}BR"
    title_label = (
        "Studio" if property_type == "Studio" else f"{bedroom_label} {property_type}"
    )
    room_label = (
        "a studio"
        if property_type == "Studio"
        else f"{bedrooms} {'bedroom' if bedrooms == 1 else 'bedrooms'}"
    )
    listing_label = "sale" if listing_type == "sale" else "annual rent"
    price_label = f"AED {price_aed:,.0f}"

    title = f"Simulated {title_label} in {community}"
    building_name = f"Synthetic {_slug(community)} Residence {index + 1:03d}"
    description = (
        f"Illustrative synthetic demo listing for {listing_label} in {community}. "
        f"The simulated {property_type.lower()} offers {room_label}, "
        f"{bathrooms} bathrooms, {area_sqft:,} square feet, and a {view_type} view. "
        f"The recorded demo price is {price_label}. This is not a genuine listing, "
        "and availability is simulated rather than verified."
    )

    return {
        "listing_id": listing_id,
        "title": title,
        "listing_type": listing_type,
        "property_type": property_type,
        "community": community,
        "building_name": building_name,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "area_sqft": area_sqft,
        "price_aed": price_aed,
        "price_per_sqft_aed": price_per_sqft_aed,
        "furnishing": furnishing,
        "view_type": view_type,
        "property_condition": condition,
        "availability_status": rng.choice(
            ("simulated_available", "simulated_on_request")
        ),
        "parking_spaces": parking_spaces,
        "amenities": amenities,
        "description": description,
        "currency": "AED",
        "source_type": "synthetic_demo",
        "is_synthetic": True,
        "demo_data_notice": DEMO_DATA_NOTICE,
        "created_date": created_date.isoformat(),
    }


def validate_listings(
    listings: list[dict[str, Any]], expected_count: int | None = None
) -> None:
    if expected_count is not None and len(listings) != expected_count:
        raise ValueError(f"expected {expected_count} listings, got {len(listings)}")

    listing_ids = [listing.get("listing_id") for listing in listings]
    if len(set(listing_ids)) != len(listing_ids):
        raise ValueError("listing IDs must be unique")

    for listing in listings:
        if set(listing) != set(REQUIRED_FIELDS):
            raise ValueError("listing fields do not match the required schema")
        if listing["listing_type"] not in LISTING_TYPES:
            raise ValueError("listing_type must be sale or rent")
        if listing["property_type"] not in PROPERTY_TYPES:
            raise ValueError("unsupported property type")
        if listing["community"] not in COMMUNITIES:
            raise ValueError("unsupported community")
        if not isinstance(listing["bedrooms"], int) or listing["bedrooms"] < 0:
            raise ValueError("bedrooms must be a non-negative integer")
        if not isinstance(listing["bathrooms"], int) or listing["bathrooms"] <= 0:
            raise ValueError("bathrooms must be a positive integer")
        if listing["area_sqft"] <= 0 or listing["price_aed"] <= 0:
            raise ValueError("area and price must be positive")
        expected_ppsf = listing["price_aed"] / listing["area_sqft"]
        if not math.isclose(listing["price_per_sqft_aed"], expected_ppsf, abs_tol=0.01):
            raise ValueError("price_per_sqft_aed does not match price_aed / area_sqft")
        if listing["currency"] != "AED":
            raise ValueError("demo listing prices must use AED")
        if listing["source_type"] != "synthetic_demo":
            raise ValueError("source_type must identify synthetic demo data")
        if listing["is_synthetic"] is not True:
            raise ValueError("all demo listings must be synthetic")
        if not listing["availability_status"].startswith("simulated_"):
            raise ValueError("availability must be labelled simulated")
        if listing["demo_data_notice"] != DEMO_DATA_NOTICE:
            raise ValueError("demo data notice is missing or incorrect")
        date.fromisoformat(listing["created_date"])


def generate_listings(
    count: int = DEFAULT_COUNT, seed: int = DEFAULT_SEED
) -> list[dict[str, Any]]:
    if count <= 0:
        raise ValueError("count must be positive")

    rng = random.Random(seed)
    listings = [_generate_record(rng, index) for index in range(count)]
    validate_listings(listings, expected_count=count)
    return listings


def _to_frame(listings: list[dict[str, Any]]) -> pd.DataFrame:
    validate_listings(listings)
    frame = pd.DataFrame(listings, columns=REQUIRED_FIELDS)
    frame["created_date"] = pd.to_datetime(frame["created_date"]).dt.date
    return frame


def write_csv(listings: list[dict[str, Any]], csv_path: str | Path) -> Path:
    path = Path(csv_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    _to_frame(listings).to_csv(path, index=False)
    return path


def import_into_duckdb(
    listings: list[dict[str, Any]], database_path: str | Path
) -> int:
    frame = _to_frame(listings)
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(path)) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        required_tables = {"secondary_sales", "dataset_provenance"}
        missing_tables = required_tables - tables
        if missing_tables:
            raise ValueError(
                "existing database is missing required historical tables: "
                f"{sorted(missing_tables)}"
            )

        preserved_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in required_tables
        }
        connection.register("demo_listings_frame", frame)
        connection.execute(
            """
            CREATE OR REPLACE TABLE demo_property_listings AS
            SELECT * FROM demo_listings_frame
            """
        )
        connection.unregister("demo_listings_frame")

        for table, expected_count in preserved_counts.items():
            actual_count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            if actual_count != expected_count:
                raise RuntimeError(f"existing table {table} was modified")

        return connection.execute(
            "SELECT COUNT(*) FROM demo_property_listings"
        ).fetchone()[0]


def generate_and_import(
    *,
    csv_path: str | Path = DEFAULT_CSV_PATH,
    database_path: str | Path | None = None,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    listings = generate_listings(count=count, seed=seed)
    written_csv = write_csv(listings, csv_path)
    database = (
        Path(database_path).expanduser().resolve()
        if database_path
        else default_database_path().resolve()
    )
    imported_rows = import_into_duckdb(listings, database)
    return {
        "csv_path": str(written_csv),
        "database_path": str(database),
        "table": "demo_property_listings",
        "row_count": imported_rows,
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and import synthetic Dubai property listings."
    )
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help="Number of listings"
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="Reproducible random seed"
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV_PATH),
        help="Output CSV path",
    )
    parser.add_argument(
        "--database",
        default=str(default_database_path()),
        help="Existing DuckDB database path",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            generate_and_import(
                csv_path=args.csv,
                database_path=args.database,
                count=args.count,
                seed=args.seed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
