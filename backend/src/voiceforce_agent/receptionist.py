from __future__ import annotations

import asyncio
import json
import logging
import textwrap
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import Any

from livekit import rtc
from livekit.agents import Agent, ChatContext, ModelSettings, RunContext, function_tool
from livekit.agents.llm import ToolError
from livekit.agents.llm.tool_context import ToolFlag

from .language_router import MultilingualTTSRouter
from .latency_metrics import LatencyRecorder
from .lead_storage import DemoLeadDatabase, LeadStorageError
from .property_search import DemoPropertyDatabase, normalize_budget_scope
from .sales_data import default_database_path
from .sales_queries import HistoricalSalesDatabase
from .state import PropertySalesSessionData

logger = logging.getLogger(__name__)


class Receptionist(Agent):
    """Prime Properties Dubai AI property sales consultant."""

    def __init__(
        self,
        *,
        latency_recorder: LatencyRecorder | None = None,
        chat_ctx: ChatContext | None = None,
    ) -> None:
        database_path = default_database_path()
        self.sales_database = HistoricalSalesDatabase(database_path)
        self.property_database = DemoPropertyDatabase(database_path)
        self.lead_database = DemoLeadDatabase(database_path)
        self.latency_recorder = latency_recorder
        super().__init__(
            instructions=textwrap.dedent(
                """\
                You are the friendly, professional AI property sales consultant for
                the Prime Properties Dubai demo.

                Speak naturally and concisely. Welcome callers and ask one useful
                follow-up question at a time. Do not interrogate callers with a
                long checklist, and do not ask again for information they already
                provided. Keep spoken replies to one or two sentences unless the
                caller asks for more detail.

                Conversation flow:
                - Understand whether the caller wants to buy or rent.
                - Collect their preferred Dubai community, property type, bedrooms,
                  bathrooms when relevant, AED budget, furnishing preference, and
                  ready or off-plan preference as they volunteer them.
                - Treat a purchase budget as a total purchase price and a rental
                  budget as an annual rental budget. Never silently mix them.
                - Use search_demo_properties once there is enough information to
                  search. Present up to three suitable results and use only the
                  returned property details in follow-up answers.
                - Omitted fields preserve preferences. Explicitly removed fields
                  must be cleared: use budget_scope="clear", clear_community,
                  clear_property_type, clear_bedrooms, or clear_furnishing.
                  Use min_bedrooms for requests such as three or more bedrooms,
                  and a list such as [2, 3] only when those exact counts are both
                  acceptable.
                - "Anywhere in Dubai", "any property type", "any bedroom count",
                  and "show me anything" mean one broad search or an inventory
                  summary, never several community-specific searches.
                - Use get_inventory_summary when the caller asks what is in the
                  system or asks to see something without useful filters.
                - If there are no matches, explain which supplied criteria produced
                  the empty result and offer to relax one filter. Do not say that
                  properties are unavailable unless live inventory is verified.

                Demo inventory rules:
                - search_demo_properties searches only the demo_property_listings
                  table. Its records are synthetic demo properties and availability
                  is simulated, not verified live inventory.
                - Demo sale prices and annual rental amounts are in AED. Clearly say
                  whether a returned amount is a purchase price or annual rent.
                - The current demo data has no ready/off-plan field. If asked about
                  that preference, acknowledge it, explain that it was not applied
                  to the search, and do not invent an answer.
                - Never invent listing IDs, prices, amenities, building details,
                  availability, owners, agents, addresses, or contact details.
                  Do not invent property availability.
                - Never claim that a simulated property is genuinely available.
                  If asked for live availability, say that this demo can recommend
                  simulated inventory but cannot verify live availability.

                Lead capture rules:
                - Offer to register an enquiry when appropriate, but do not save a
                  lead merely because a caller mentioned a phone number.
                - Before calling capture_customer_lead, ask for explicit permission
                  to save the enquiry, repeat the customer's name and phone number,
                  and obtain confirmation that both are correct.
                - Call capture_customer_lead only when the caller has consented and
                  confirmed the details. Never fabricate missing information.
                - Use the selected listing IDs returned by search_demo_properties;
                  do not create IDs yourself.
                - After a successful result, confirm that the demo enquiry was
                  registered. If the tool reports a duplicate or an error, explain
                  that clearly without claiming success.

                Historical sales tools are available for questions about the
                secondary_sales.csv dataset. Those tools describe historical dataset records and
                recorded dataset prices in USD, not current listings or
                verified asking prices. The source documentation describes those
                records as generated for analysis, not verified Dubai Land
                Department transactions. Say USD for historical results and never
                label them AED or use them to answer current availability questions.

                Use plain spoken English without markdown, emojis, or lists.

                Language behavior:
                - Reply in the language used by the caller: English, Pakistani
                  Urdu, or Arabic. Keep the current language until the caller
                  clearly switches.
                - Do not translate Urdu or Arabic into English unless the caller
                  asks for a translation.
                - For Roman Urdu, understand the caller's Latin-script Urdu and
                  reply in natural Pakistani Urdu using the caller's script when
                  practical. For Urdu-script input, reply in Urdu script.
                - Hindi is temporarily disabled. If STT labels an Urdu turn as
                  Hindi (hi or hi-IN), or presents the turn in Devanagari,
                  treat it as Pakistani Urdu and reply only in Urdu script.
                  Never generate Hindi or Devanagari response text for this
                  application. Preserve the caller's original transcription;
                  this rule controls the response language only.
                - Reply in Arabic script for Arabic input, using clear UAE-
                  appropriate conversational Arabic while preserving names,
                  numbers, prices, addresses, and property details.
                - Keep replies concise and natural for streaming voice output.
                """
            ),
            chat_ctx=chat_ctx,
        )

    language_router: MultilingualTTSRouter | None = None

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncIterator[rtc.AudioFrame]:
        """Use the session's selected language TTS at synthesis time.

        The server attaches the router after constructing this agent.  The
        router is intentionally kept as runtime state rather than added to the
        prompt or transcript.
        """

        router = self.language_router
        if router is not None:
            async for frame in router.tts_node(text, model_settings, agent=self):
                yield frame
            return

        async for frame in Agent.default.tts_node(self, text, model_settings):
            yield frame

    @staticmethod
    def _context_ids(context: RunContext[Any]) -> tuple[str | None, str | None]:
        function_call = getattr(context, "function_call", None)
        speech_handle = getattr(context, "speech_handle", None)
        return (
            getattr(function_call, "call_id", None),
            getattr(speech_handle, "id", None),
        )

    def _tool_stage_start(
        self, context: RunContext[Any], stage: str, tool_name: str
    ) -> float:
        started_at = time.monotonic()
        if self.latency_recorder is not None:
            call_id, speech_id = self._context_ids(context)
            self.latency_recorder.record_metric(
                stage="tool",
                metric="tool_stage_started",
                value=1,
                unit="event",
                source=f"{tool_name}.{stage}",
                request_id=call_id,
                speech_id=speech_id,
                labels={"tool_name": tool_name, "stage": stage},
            )
        return started_at

    def _tool_stage_end(
        self,
        context: RunContext[Any],
        stage: str,
        tool_name: str,
        started_at: float,
        *,
        status: str = "ok",
        labels: dict[str, Any] | None = None,
    ) -> None:
        if self.latency_recorder is None:
            return
        call_id, speech_id = self._context_ids(context)
        stage_labels = {"tool_name": tool_name, "stage": stage, "status": status}
        if labels:
            stage_labels.update(labels)
        self.latency_recorder.record_metric(
            stage="tool",
            metric="tool_stage_duration",
            value=max(0.0, time.monotonic() - started_at),
            unit="seconds",
            source=f"{tool_name}.{stage}",
            request_id=call_id,
            speech_id=speech_id,
            labels=stage_labels,
        )
        self.latency_recorder.record_metric(
            stage="tool",
            metric="tool_stage_completed",
            value=1,
            unit="event",
            source=f"{tool_name}.{stage}",
            request_id=call_id,
            speech_id=speech_id,
            labels=stage_labels,
        )

    def _record_tool_value(
        self,
        context: RunContext[Any],
        metric: str,
        value: int | float,
        unit: str,
        tool_name: str,
        *,
        labels: dict[str, Any] | None = None,
    ) -> None:
        if self.latency_recorder is None:
            return
        call_id, speech_id = self._context_ids(context)
        value_labels = {"tool_name": tool_name}
        if labels:
            value_labels.update(labels)
        self.latency_recorder.record_metric(
            stage="tool",
            metric=metric,
            value=value,
            unit=unit,
            source=f"{tool_name}.result",
            request_id=call_id,
            speech_id=speech_id,
            labels=value_labels,
        )

    async def _run_sales_tool(
        self, operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
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

    async def _run_property_tool(
        self, operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        try:
            return await asyncio.to_thread(operation, *args, **kwargs)
        except FileNotFoundError as error:
            raise ToolError(
                "The synthetic demo inventory is not loaded yet. Please try again "
                "after the demo data has been prepared."
            ) from error
        except ValueError as error:
            raise ToolError(str(error)) from error
        except Exception as error:
            logger.exception("Demo property search failed")
            raise ToolError(
                "The demo property search failed. Please try adjusting the criteria."
            ) from error

    @staticmethod
    def _ensure_json_serializable(result: Any) -> Any:
        try:
            json.dumps(result)
        except (TypeError, ValueError) as error:
            logger.exception("Demo property search returned invalid output")
            raise ToolError(
                "I could not complete the demo property search. Please try again "
                "or adjust one filter."
            ) from error
        return result

    async def _run_lead_tool(
        self, operation: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        try:
            return await asyncio.to_thread(operation, *args, **kwargs)
        except ValueError as error:
            raise ToolError(str(error)) from error
        except (FileNotFoundError, LeadStorageError) as error:
            raise ToolError(
                "The demo enquiry could not be saved right now. Please try again later."
            ) from error
        except Exception as error:
            logger.exception("Demo lead capture failed")
            raise ToolError(
                "The demo enquiry could not be saved right now. Please try again later."
            ) from error

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def search_demo_properties(
        self,
        context: RunContext[PropertySalesSessionData],
        transaction_intent: str | None = None,
        community: str | None = None,
        property_type: str | None = None,
        bedrooms: int | list[int] | None = None,
        min_bedrooms: int | None = None,
        bathrooms: int | None = None,
        min_budget_aed: float | None = None,
        max_budget_aed: float | None = None,
        budget_scope: str | None = None,
        furnishing: str | None = None,
        ready_or_offplan_preference: str | None = None,
        limit: int = 3,
        clear_community: bool = False,
        clear_furnishing: bool = False,
        clear_property_type: bool = False,
        clear_bedrooms: bool = False,
    ) -> dict[str, Any]:
        """Search synthetic demo properties using the caller's preferences.

        Use this for simulated demo inventory after the caller's buy-or-rent
        intent is understood. Prices are in AED: sale results are purchase
        prices and rent results are annual rents. The tool returns facts from
        DuckDB, including simulated availability; it never verifies live
        inventory. Supported property types are apartment, villa, townhouse,
        penthouse, and studio. Pass bedrooms as an integer for an exact match, a
        list such as [2, 3] when either exact count is acceptable, or use
        min_bedrooms for requests such as three or more. Use budget_scope="set"
        with a budget, budget_scope="clear" when the caller removes the budget,
        and budget_scope="keep" only when preserving it. If the caller says
        anywhere in Dubai, set clear_community to true. Use clear_property_type
        or clear_bedrooms when the caller removes those constraints. If the
        caller says either furnishing, set clear_furnishing to true. Omitted
        fields preserve existing call preferences. The demo schema has no
        ready/off-plan field.
        """
        tool_name = "search_demo_properties"
        execution_started = self._tool_stage_start(
            context, "tool_execution_started", tool_name
        )
        try:
            preferences = context.userdata
            validation_started = self._tool_stage_start(
                context, "input_validation", tool_name
            )
            validation_status = "ok"
            try:
                requested_budget_scope = normalize_budget_scope(
                    budget_scope, min_budget_aed, max_budget_aed
                )
                if not isinstance(clear_property_type, bool):
                    raise ValueError("clear_property_type must be a boolean")
                if not isinstance(clear_bedrooms, bool):
                    raise ValueError("clear_bedrooms must be a boolean")
                transaction_for_query = (
                    transaction_intent
                    if transaction_intent is not None
                    else preferences.transaction_intent
                )
                transaction_changed = (
                    isinstance(transaction_for_query, str)
                    and isinstance(preferences.transaction_intent, str)
                    and transaction_for_query.casefold()
                    != preferences.transaction_intent.casefold()
                )
                if transaction_changed and requested_budget_scope == "keep":
                    requested_budget_scope = "clear"
            except ValueError:
                validation_status = "invalid"
                raise
            except Exception:
                validation_status = "error"
                raise
            finally:
                self._tool_stage_end(
                    context,
                    "input_validation",
                    tool_name,
                    validation_started,
                    status=validation_status,
                )

            effective_transaction_intent = transaction_for_query
            effective_community = (
                None
                if clear_community
                else (
                    community
                    if community is not None
                    else preferences.preferred_community
                )
            )
            effective_property_type = (
                None
                if clear_property_type
                else (
                    property_type
                    if property_type is not None
                    else preferences.property_type
                )
            )
            if clear_bedrooms:
                effective_bedrooms = None
                effective_min_bedrooms = None
            elif min_bedrooms is not None:
                effective_bedrooms = None
                effective_min_bedrooms = min_bedrooms
            elif bedrooms is not None:
                effective_bedrooms = bedrooms
                effective_min_bedrooms = None
            elif preferences.minimum_bedrooms is not None:
                effective_bedrooms = None
                effective_min_bedrooms = preferences.minimum_bedrooms
            else:
                effective_bedrooms = (
                    preferences.bedroom_counts
                    if preferences.bedroom_counts is not None
                    else preferences.bedrooms
                )
                effective_min_bedrooms = None
            effective_bathrooms = (
                bathrooms if bathrooms is not None else preferences.bathrooms
            )
            if requested_budget_scope == "clear":
                effective_minimum = None
                effective_maximum = None
                query_budget_scope = "clear"
            elif requested_budget_scope == "set":
                effective_minimum = min_budget_aed
                effective_maximum = max_budget_aed
                query_budget_scope = "set"
            else:
                effective_minimum = preferences.minimum_budget_aed
                effective_maximum = preferences.maximum_budget_aed
                query_budget_scope = (
                    "set"
                    if effective_minimum is not None or effective_maximum is not None
                    else "clear"
                )
            effective_furnishing = (
                None
                if clear_furnishing
                else (
                    furnishing
                    if furnishing is not None
                    else preferences.furnishing_preference
                )
            )
            effective_readiness = (
                ready_or_offplan_preference
                if ready_or_offplan_preference is not None
                else preferences.ready_or_offplan_preference
            )

            normalization_started = self._tool_stage_start(
                context, "filter_normalization", tool_name
            )
            try:
                request = self.property_database.normalize_request(
                    transaction_intent=effective_transaction_intent,
                    community=effective_community,
                    property_type=effective_property_type,
                    bedrooms=effective_bedrooms,
                    min_bedrooms=effective_min_bedrooms,
                    bathrooms=effective_bathrooms,
                    min_budget_aed=effective_minimum,
                    max_budget_aed=effective_maximum,
                    budget_scope=query_budget_scope,
                    furnishing=effective_furnishing,
                    ready_or_offplan_preference=effective_readiness,
                    limit=limit,
                    clear_community=clear_community,
                    clear_furnishing=clear_furnishing,
                    clear_property_type=clear_property_type,
                    clear_bedrooms=clear_bedrooms,
                )
                normalized_filters = json.dumps(
                    request.filters, sort_keys=True, separators=(",", ":")
                )
            except ValueError:
                self._tool_stage_end(
                    context,
                    "filter_normalization",
                    tool_name,
                    normalization_started,
                    status="invalid",
                )
                raise
            except Exception:
                self._tool_stage_end(
                    context,
                    "filter_normalization",
                    tool_name,
                    normalization_started,
                    status="error",
                )
                raise
            self._tool_stage_end(
                context,
                "filter_normalization",
                tool_name,
                normalization_started,
                labels={"normalized_filters": normalized_filters},
            )

            state_filters = dict(request.filters)
            state_filters["budget_scope"] = requested_budget_scope
            context.userdata.update_from_search(state_filters)

            query_started = self._tool_stage_start(context, "database_query", tool_name)
            try:
                result, query_metrics = await self._run_property_tool(
                    self.property_database.search_normalized, request
                )
            except ToolError:
                self._tool_stage_end(
                    context,
                    "database_query",
                    tool_name,
                    query_started,
                    status="error",
                )
                raise
            self._tool_stage_end(
                context,
                "database_query",
                tool_name,
                query_started,
                labels={"normalized_filters": normalized_filters},
            )
            self._record_tool_value(
                context,
                "database_row_count",
                query_metrics["match_count"],
                "count",
                tool_name,
                labels={"normalized_filters": normalized_filters},
            )
            self._record_tool_value(
                context,
                "database_query_duration",
                query_metrics["query_duration_seconds"],
                "seconds",
                tool_name,
            )
            self._record_tool_value(
                context,
                "sql_parameter_count",
                query_metrics["sql_parameter_count"],
                "count",
                tool_name,
            )

            processing_started = self._tool_stage_start(
                context, "result_processing", tool_name
            )
            result["filters"]["budget_scope"] = requested_budget_scope
            self._tool_stage_end(
                context,
                "result_processing",
                tool_name,
                processing_started,
                labels={
                    "status": result["status"],
                    "normalized_filters": normalized_filters,
                },
            )
            serialization_started = self._tool_stage_start(
                context, "serialization", tool_name
            )
            try:
                result = self._ensure_json_serializable(result)
            except ToolError:
                self._tool_stage_end(
                    context,
                    "serialization",
                    tool_name,
                    serialization_started,
                    status="error",
                )
                raise
            self._tool_stage_end(
                context, "serialization", tool_name, serialization_started
            )
            self._record_tool_value(
                context,
                "result_count",
                result["result_count"],
                "count",
                tool_name,
                labels={"status": result["status"]},
            )
            self._record_tool_value(
                context,
                "payload_bytes",
                len(json.dumps(result, separators=(",", ":")).encode()),
                "bytes",
                tool_name,
            )
            returned_started = self._tool_stage_start(
                context, "tool_result_returned", tool_name
            )
            self._tool_stage_end(
                context, "tool_result_returned", tool_name, returned_started
            )
            return result
        except ToolError:
            self._tool_stage_end(
                context,
                "tool_execution_started",
                tool_name,
                execution_started,
                status="error",
            )
            raise
        except ValueError as error:
            self._tool_stage_end(
                context,
                "tool_execution_started",
                tool_name,
                execution_started,
                status="invalid",
            )
            raise ToolError(str(error)) from error
        except Exception as error:
            logger.exception("Demo property search failed before tool completion")
            self._tool_stage_end(
                context,
                "tool_execution_started",
                tool_name,
                execution_started,
                status="error",
            )
            raise ToolError(
                "The demo property search failed. Please try adjusting the criteria."
            ) from error

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def get_inventory_summary(
        self, context: RunContext[PropertySalesSessionData]
    ) -> dict[str, Any]:
        """Show actual synthetic demo inventory capabilities and aggregate counts.

        Use this when the caller asks what the system has, asks to show anything,
        or removes enough filters that a broad discovery response is more useful
        than another narrow search. This describes synthetic demo inventory only;
        it does not verify live availability and does not include historical sales.
        """
        tool_name = "get_inventory_summary"
        execution_started = self._tool_stage_start(
            context, "tool_execution_started", tool_name
        )
        try:
            query_started = self._tool_stage_start(context, "database_query", tool_name)
            try:
                result = await self._run_property_tool(
                    self.property_database.inventory_summary
                )
            except ToolError:
                self._tool_stage_end(
                    context,
                    "database_query",
                    tool_name,
                    query_started,
                    status="error",
                )
                raise
            self._tool_stage_end(context, "database_query", tool_name, query_started)
            self._record_tool_value(
                context,
                "database_row_count",
                result["total_records"],
                "count",
                tool_name,
            )
            serialization_started = self._tool_stage_start(
                context, "serialization", tool_name
            )
            result = self._ensure_json_serializable(result)
            self._tool_stage_end(
                context, "serialization", tool_name, serialization_started
            )
            self._record_tool_value(
                context,
                "payload_bytes",
                len(json.dumps(result, separators=(",", ":")).encode()),
                "bytes",
                tool_name,
            )
            returned_started = self._tool_stage_start(
                context, "tool_result_returned", tool_name
            )
            self._tool_stage_end(
                context, "tool_result_returned", tool_name, returned_started
            )
            return result
        except ToolError:
            self._tool_stage_end(
                context,
                "tool_execution_started",
                tool_name,
                execution_started,
                status="error",
            )
            raise
        except Exception as error:
            logger.exception("Demo inventory summary failed before tool completion")
            self._tool_stage_end(
                context,
                "tool_execution_started",
                tool_name,
                execution_started,
                status="error",
            )
            raise ToolError(
                "I could not inspect the demo inventory right now. Please try again."
            ) from error

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def capture_customer_lead(
        self,
        context: RunContext[PropertySalesSessionData],
        customer_name: str,
        phone_number: str,
        customer_consent: bool,
        confirmed_contact_details: bool,
        transaction_intent: str | None = None,
        preferred_community: str | None = None,
        property_type: str | None = None,
        bedrooms: int | None = None,
        minimum_budget_aed: float | None = None,
        maximum_budget_aed: float | None = None,
        furnishing_preference: str | None = None,
        selected_listing_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save a demo enquiry only after explicit consent and contact confirmation.

        Call this only after the customer agrees that their information may be
        saved and confirms their name and phone number. Use actual returned demo
        listing IDs when available. Do not fabricate missing preferences or
        contact details; transaction intent is required and budgets are AED,
        with rental budgets interpreted as annual rent.
        """
        context.disallow_interruptions()
        preferences = context.userdata
        return await self._run_lead_tool(
            self.lead_database.capture,
            customer_name=customer_name,
            phone_number=phone_number,
            customer_consent=customer_consent,
            confirmed_contact_details=confirmed_contact_details,
            transaction_intent=transaction_intent or preferences.transaction_intent,
            preferred_community=(
                preferred_community
                if preferred_community is not None
                else preferences.preferred_community
            ),
            property_type=(
                property_type
                if property_type is not None
                else preferences.property_type
            ),
            bedrooms=bedrooms if bedrooms is not None else preferences.bedrooms,
            minimum_budget_aed=(
                minimum_budget_aed
                if minimum_budget_aed is not None
                else preferences.minimum_budget_aed
            ),
            maximum_budget_aed=(
                maximum_budget_aed
                if maximum_budget_aed is not None
                else preferences.maximum_budget_aed
            ),
            furnishing_preference=(
                furnishing_preference
                if furnishing_preference is not None
                else preferences.furnishing_preference
            ),
            selected_listing_ids=(
                selected_listing_ids
                if selected_listing_ids is not None
                else preferences.selected_listing_ids
            ),
        )

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
        community or zone. Never use this tool to claim current availability.
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
        """Summarize historical dataset records and prices for one area.

        Use year or month granularity for historical averages and medians. Prices
        are recorded in USD; say USD and do not convert them. This tool cannot
        report live inventory.
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
        """Compare historical dataset records and prices between two areas.

        Return only the historical comparison. Prices are recorded in USD; say
        USD and do not convert them. Do not infer current inventory or asking
        prices from the result.
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
