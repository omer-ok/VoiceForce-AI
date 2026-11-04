from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .sales_data import (
    DATASET_GENERATION_NOTE,
    PRICE_CURRENCY,
    PRICE_CURRENCY_NOTE,
    default_database_path,
)


class HistoricalSalesDatabase:
    """Parameterized DuckDB queries over the cleaned secondary sales table."""

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
                f"Historical sales database not found: {self.database_path}"
            )
        return duckdb.connect(str(self.database_path), read_only=True)

    @staticmethod
    def _text(value: str | None, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        result = value.strip()
        if not result:
            raise ValueError(f"{field} cannot be empty")
        if len(result) > 120:
            raise ValueError(f"{field} is too long")
        return result

    @staticmethod
    def _number(value: float | int | None, field: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number")
        if value < 0:
            raise ValueError(f"{field} cannot be negative")
        return float(value)

    @staticmethod
    def _bedrooms(value: int | None) -> int | None:
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 20
        ):
            raise ValueError("bedrooms must be an integer from 0 to 20")
        return value

    @staticmethod
    def _date(value: str | None, field: str) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field} must use YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must use YYYY-MM-DD") from error

    @classmethod
    def _where(
        cls,
        *,
        area: str | None = None,
        property_type: str | None = None,
        min_price_usd: float | int | None = None,
        max_price_usd: float | int | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[str, list[Any], dict[str, Any]]:
        normalized_area = cls._text(area, "area")
        normalized_property_type = cls._text(property_type, "property_type")
        minimum = cls._number(min_price_usd, "min_price_usd")
        maximum = cls._number(max_price_usd, "max_price_usd")
        bedroom_count = cls._bedrooms(bedrooms)
        start = cls._date(start_date, "start_date")
        end = cls._date(end_date, "end_date")

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("min_price_usd cannot exceed max_price_usd")
        if start is not None and end is not None and start > end:
            raise ValueError("start_date cannot be after end_date")

        clauses = ["TRUE"]
        parameters: list[Any] = []
        filters: dict[str, Any] = {}

        if normalized_area:
            clauses.append("(lower(community) = lower(?) OR lower(zone) = lower(?))")
            parameters.extend([normalized_area, normalized_area])
            filters["area"] = normalized_area

        if normalized_property_type:
            if normalized_property_type.lower() in {"apartment", "villa"}:
                clauses.append("lower(property_category) = lower(?)")
            else:
                clauses.append("lower(property_type) = lower(?)")
            parameters.append(normalized_property_type)
            filters["property_type"] = normalized_property_type

        if minimum is not None:
            clauses.append("price_usd >= ?")
            parameters.append(minimum)
            filters["min_price_usd"] = minimum

        if maximum is not None:
            clauses.append("price_usd <= ?")
            parameters.append(maximum)
            filters["max_price_usd"] = maximum

        if bedroom_count is not None:
            clauses.append("bedrooms = ?")
            parameters.append(bedroom_count)
            filters["bedrooms"] = bedroom_count

        if start is not None:
            clauses.append("date_listed >= ?")
            parameters.append(start)
            filters["start_date"] = start.isoformat()

        if end is not None:
            clauses.append("date_listed <= ?")
            parameters.append(end)
            filters["end_date"] = end.isoformat()

        return " AND ".join(clauses), parameters, filters

    @staticmethod
    def _value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, "item"):
            return value.item()
        return value

    @classmethod
    def _rows(cls, cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
        columns = [description[0] for description in cursor.description]
        return [
            {
                column: cls._value(value)
                for column, value in zip(columns, row, strict=True)
            }
            for row in cursor.fetchall()
        ]

    def _summary(
        self,
        connection: duckdb.DuckDBPyConnection,
        where: str,
        parameters: list[Any],
    ) -> dict[str, Any]:
        result = connection.execute(
            f"""
            SELECT
                COUNT(*)::BIGINT AS record_count,
                AVG(price_usd) AS average_price_usd,
                MEDIAN(price_usd) AS median_price_usd,
                AVG(price_per_sqft_usd) AS average_price_per_sqft_usd,
                MEDIAN(price_per_sqft_usd) AS median_price_per_sqft_usd,
                MIN(date_listed) AS earliest_date,
                MAX(date_listed) AS latest_date
            FROM secondary_sales
            WHERE {where}
            """,
            parameters,
        ).fetchone()
        keys = (
            "record_count",
            "average_price_usd",
            "median_price_usd",
            "average_price_per_sqft_usd",
            "median_price_per_sqft_usd",
            "earliest_date",
            "latest_date",
        )
        return {
            key: self._value(value) for key, value in zip(keys, result, strict=True)
        }

    def search(
        self,
        *,
        area: str | None = None,
        property_type: str | None = None,
        min_price_usd: float | int | None = None,
        max_price_usd: float | int | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 20
        ):
            raise ValueError("limit must be an integer from 1 to 20")

        where, parameters, filters = self._where(
            area=area,
            property_type=property_type,
            min_price_usd=min_price_usd,
            max_price_usd=max_price_usd,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
        )

        with self._connect() as connection:
            summary = self._summary(connection, where, parameters)
            sample_cursor = connection.execute(
                f"""
                SELECT id, date_listed, community, zone, property_category,
                       property_type, bedrooms, area_sqft, price_usd,
                       price_per_sqft_usd, condition
                FROM secondary_sales
                WHERE {where}
                ORDER BY date_listed DESC, id
                LIMIT ?
                """,
                [*parameters, limit],
            )
            samples = self._rows(sample_cursor)

        return {
            "dataset": "secondary_sales.csv",
            "historical_only": True,
            "price_currency": PRICE_CURRENCY,
            "filters": filters,
            "summary": summary,
            "sample_records": samples,
            "currency_note": PRICE_CURRENCY_NOTE,
            "availability_note": (
                "These are historical dataset records with recorded dataset prices, "
                "not current property listings or verified asking prices. They are "
                f"not verified Dubai Land Department transactions. {DATASET_GENERATION_NOTE}"
            ),
        }

    def market_insights(
        self,
        *,
        area: str,
        property_type: str | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        granularity: str = "year",
    ) -> dict[str, Any]:
        if granularity not in {"month", "year"}:
            raise ValueError("granularity must be month or year")

        where, parameters, filters = self._where(
            area=area,
            property_type=property_type,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
        )
        period_expression = f"date_trunc('{granularity}', date_listed)"

        with self._connect() as connection:
            summary = self._summary(connection, where, parameters)
            trend_cursor = connection.execute(
                f"""
                SELECT
                    CAST({period_expression} AS DATE) AS period,
                    COUNT(*)::BIGINT AS record_count,
                    AVG(price_usd) AS average_price_usd,
                    MEDIAN(price_usd) AS median_price_usd,
                    AVG(price_per_sqft_usd) AS average_price_per_sqft_usd
                FROM secondary_sales
                WHERE {where}
                GROUP BY period
                ORDER BY period
                """,
                parameters,
            )
            trend = self._rows(trend_cursor)

        return {
            "dataset": "secondary_sales.csv",
            "historical_only": True,
            "price_currency": PRICE_CURRENCY,
            "filters": {**filters, "granularity": granularity},
            "summary": summary,
            "trend": trend,
            "currency_note": PRICE_CURRENCY_NOTE,
            "availability_note": (
                "The trend describes historical dataset records and recorded dataset "
                "prices; it does not establish current availability. They are not "
                f"verified Dubai Land Department transactions. {DATASET_GENERATION_NOTE}"
            ),
        }

    def compare_areas(
        self,
        *,
        area_a: str,
        area_b: str,
        property_type: str | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        normalized_a = self._text(area_a, "area_a")
        normalized_b = self._text(area_b, "area_b")
        if normalized_a.casefold() == normalized_b.casefold():
            raise ValueError("area_a and area_b must be different")

        comparisons = []
        with self._connect() as connection:
            for label in (normalized_a, normalized_b):
                where, parameters, filters = self._where(
                    area=label,
                    property_type=property_type,
                    bedrooms=bedrooms,
                    start_date=start_date,
                    end_date=end_date,
                )
                comparisons.append(
                    {
                        "area": label,
                        "filters": filters,
                        "summary": self._summary(connection, where, parameters),
                    }
                )

        return {
            "dataset": "secondary_sales.csv",
            "historical_only": True,
            "price_currency": PRICE_CURRENCY,
            "areas": comparisons,
            "currency_note": PRICE_CURRENCY_NOTE,
            "availability_note": (
                "This comparison uses historical dataset records and recorded dataset "
                "prices only; it does not verify current listings. They are not "
                f"verified Dubai Land Department transactions. {DATASET_GENERATION_NOTE}"
            ),
        }
