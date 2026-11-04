import asyncio
import logging
import textwrap
from typing import Any

from livekit.agents import Agent, RunContext, function_tool
from livekit.agents.llm import ToolError
from livekit.agents.llm.tool_context import ToolFlag

from .sales_queries import HistoricalSalesDatabase

logger = logging.getLogger(__name__)


class Receptionist(Agent):
    """Prime Properties Dubai receptionist with historical sales tools."""

    def __init__(self) -> None:
        self.sales_database = HistoricalSalesDatabase()
        super().__init__(
            instructions=textwrap.dedent(
                """\
                You are the friendly AI receptionist for Prime Properties Dubai.

                Speak naturally and concisely. Welcome callers, understand why
                they are calling, and help them take the next simple step. Ask
                one question at a time and keep spoken replies to one or two
                sentences unless the caller asks for more detail.

                Historical sales tools are available for the secondary_sales.csv
                dataset. Use them for historical sales-data questions and
                clearly explain that their results are historical dataset records,
                not current listings or verified asking prices. The source
                documentation describes the records as generated for analysis,
                not verified Dubai Land Department transactions.

                All recorded dataset prices are in USD. Say USD when speaking
                about prices, and never label these values as AED. Do not convert
                currencies.

                Do not invent property availability, prices, listing IDs,
                appointments, or customer records. If a caller asks for a
                currently available property, explain that this initial dataset
                cannot verify live availability and offer to take down their
                requirements for a team member to follow up.

                Never present historical sales prices as current market offers.
                Do not use historical tools to answer whether a specific
                property is currently available.

                Use plain spoken English without markdown, emojis, or lists.
                """
            )
        )

    async def _run_sales_tool(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(operation, *args, **kwargs)
        except FileNotFoundError as error:
            raise ToolError(
                "Historical sales data is not loaded yet. The team needs to run "
                "the sales ingestion step before I can answer that."
            ) from error
        except ValueError as error:
            raise ToolError(str(error)) from error
        except Exception as error:
            logger.exception("Historical sales tool failed")
            raise ToolError(
                "The historical sales lookup failed. Please try again later."
            ) from error

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def search_historical_sales(
        self,
        context: RunContext,
        area: str | None = None,
        property_type: str | None = None,
        min_price_usd: float | None = None,
        max_price_usd: float | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Search historical secondary sales using the available filters.

        Use this only for historical sales-data questions. Results are historical
        dataset records and recorded dataset prices in USD; explicitly say USD
        in spoken replies and do not convert currencies. The area may be a
        community or zone. Property type accepts values such as apartment,
        villa, studio, 1BR, 2BR, or 4BR_penthouse. Never use this tool to claim
        that a property is currently available.
        """
        del context
        return await self._run_sales_tool(
            self.sales_database.search,
            area=area,
            property_type=property_type,
            min_price_usd=min_price_usd,
            max_price_usd=max_price_usd,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def get_market_insights(
        self,
        context: RunContext,
        area: str,
        property_type: str | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        granularity: str = "year",
    ) -> dict[str, Any]:
        """Summarize historical dataset records and prices for one community or zone.

        Use year or month granularity for historical averages, medians, and
        price-per-square-foot trends. Prices are recorded in USD; say USD and
        do not convert them. This tool cannot report live inventory.
        """
        del context
        return await self._run_sales_tool(
            self.sales_database.market_insights,
            area=area,
            property_type=property_type,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def compare_areas(
        self,
        context: RunContext,
        area_a: str,
        area_b: str,
        property_type: str | None = None,
        bedrooms: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Compare historical dataset records and prices between two communities or zones.

        Return the historical dataset comparison only. Prices are recorded in
        USD; say USD and do not convert them. Do not infer current inventory or
        current asking prices from the result.
        """
        del context
        return await self._run_sales_tool(
            self.sales_database.compare_areas,
            area_a=area_a,
            area_b=area_b,
            property_type=property_type,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
        )
