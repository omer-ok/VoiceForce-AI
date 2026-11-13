from __future__ import annotations

import asyncio
import json
import logging
import textwrap
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from livekit import rtc
from livekit.agents import Agent, ChatContext, ModelSettings, RunContext, function_tool
from livekit.agents.llm import ToolError, ToolResult
from livekit.agents.llm.tool_context import ToolFlag

from .config import configured_fast_property_results
from .fast_property_reply import render_demo_result
from .language_router import MultilingualTTSRouter
from .latency_metrics import LatencyRecorder
from .lead_storage import DemoLeadDatabase, LeadStorageError
from .property_search import DemoPropertyDatabase, normalize_budget_scope
from .sales_data import default_database_path
from .sales_queries import HistoricalSalesDatabase
from .state import PropertySalesSessionData

logger = logging.getLogger(__name__)

LLM_CONTEXT_MAX_ITEMS = 12
DEMO_TOOL_NAMES = frozenset(
    {
        "search_demo_properties",
        "get_inventory_summary",
        "capture_customer_lead",
        "switch_data_scope",
    }
)
HISTORICAL_TOOL_NAMES = frozenset(
    {
        "search_historical_sales",
        "get_market_insights",
        "compare_areas",
        "capture_customer_lead",
        "switch_data_scope",
    }
)

RECEPTIONIST_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are the friendly, professional Prime Properties Dubai receptionist and
    property consultant. Speak naturally in the caller's current language:
    English, Pakistani Urdu, or Arabic; English is the default.

    Be concise. Use plain spoken language, ask one focused question at
    a time, ask only for missing or ambiguous details, and do not repeat facts.
    Avoid markdown, emojis, filler, and long introductions.

    Search:
    - Establish buy versus rent, then gather only useful filters: community,
      property type, bedrooms, bathrooms, AED budget, furnishing, and
      ready/off-plan preference. A sale budget is total price; a rent budget is
      annual rent.
    - When ready, call search_demo_properties. Lead with one result's key facts;
      offer more. Use only returned facts. Omitted fields preserve preferences; use clear_* or
      budget_scope="clear" when the caller removes a filter. Use min_bedrooms for
      "or more" and a bedroom list for exact alternatives. "Anywhere in Dubai",
      "any property type", and "show me anything" mean one broad search or
      get_inventory_summary, not repeated community searches.
    - For no results, name the criteria that failed and offer to relax one filter.
      Never claim live availability.

    Grounding:
    - Demo tools use synthetic data. Say availability is simulated, not verified.
      Sale prices and annual rents are AED; say which one you quote.
      Never invent IDs, prices, features, amenities, addresses or contacts.
      Do not invent property availability. This demo cannot verify live availability.
    - The demo schema has no ready/off-plan field. Say that preference was
      recorded but not applied; never invent an answer.
    - Historical sales tools are available only for secondary-sales questions
      about historical dataset records: use search_historical_sales,
      get_market_insights, and compare_areas. These generated records are not
      verified Dubai Land Department transactions, are
      priced in USD, not AED, and are never current listings or proof of
      availability.

    Lead and privacy:
    Offer an enquiry when appropriate, but interest or a phone number alone is not
    consent. Call capture_customer_lead only after the caller explicitly agrees to save
    the enquiry and confirms their name and phone number. Never invent contact
    details or listing IDs; use IDs returned by search. After success say the demo
    enquiry was registered; never claim success for a duplicate or error.

    Language:
    Stay in the current language until the caller clearly switches. Understand
    Roman Urdu and reply in natural Pakistani Urdu; use Urdu script for Urdu
    input. Treat hi/hi-IN and Devanagari as the existing Urdu compatibility case.
    Never generate Hindi or Devanagari response text. Reply in Arabic script for
    Arabic, preserving names, numbers, prices, addresses, and property details.
    """
)


class Receptionist(Agent):
    """Prime Properties Dubai AI property sales consultant."""

    def __init__(
        self,
        *,
        latency_recorder: LatencyRecorder | None = None,
        chat_ctx: ChatContext | None = None,
        session_data: PropertySalesSessionData | None = None,
    ) -> None:
        database_path = default_database_path()
        self.sales_database = HistoricalSalesDatabase(database_path)
        self.property_database = DemoPropertyDatabase(database_path)
        self.lead_database = DemoLeadDatabase(database_path)
        self.latency_recorder = latency_recorder
        self.session_data = session_data
        self._acknowledged_speech_id: str | None = None
        super().__init__(
            instructions=RECEPTIONIST_SYSTEM_PROMPT,
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

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list[Any],
        model_settings: ModelSettings,
    ) -> AsyncIterator[Any]:
        """Generate from a bounded request context without changing session history.

        The SDK reuses a preemptive generation only when the context and registered
        tool set are unchanged.  Trimming a copy here keeps speculative LLM/TTS
        generation eligible while preventing old turns from growing every request.
        """

        request_ctx = chat_ctx.copy()
        request_ctx.truncate(max_items=LLM_CONTEXT_MAX_ITEMS)
        if self.session_data is not None:
            request_ctx.add_message(
                role="developer",
                content=self._compact_session_state(),
            )

        scoped_tools, tool_mode = self._tools_for_request(tools)
        if self.latency_recorder is not None:
            self.latency_recorder.record_metric(
                stage="llm",
                metric="request_context_items",
                value=len(request_ctx.items),
                unit="count",
                source="receptionist.llm_node",
                labels={
                    "context_max_items": LLM_CONTEXT_MAX_ITEMS,
                    "tool_mode": tool_mode,
                    "tool_count": len(scoped_tools),
                },
            )

        async for chunk in Agent.default.llm_node(
            self,
            request_ctx,
            scoped_tools,
            model_settings,
        ):
            yield chunk

    def _compact_session_state(self) -> str:
        """Return only non-PII state needed to preserve search continuity."""

        state = self.session_data
        if state is None:
            return "Internal call state is unavailable; rely only on the conversation and tool results."

        def value_or_unset(value: object) -> str:
            if value is None or value == "":
                return "unset"
            if isinstance(value, list):
                return ",".join(str(item) for item in value) or "unset"
            return str(value).replace("\n", " ")

        bedrooms = state.bedroom_counts or state.bedrooms or state.minimum_bedrooms
        selected_ids = ",".join(state.selected_listing_ids[:3]) or "none"
        demo_results = json.dumps(state.last_demo_results[:5], ensure_ascii=False)
        return (
            "Internal call state; do not mention this block. Preserve these filters "
            "when the caller omits them: "
            f"scope={value_or_unset(state.data_scope)}; "
            f"intent={value_or_unset(state.transaction_intent)}; "
            f"community={value_or_unset(state.preferred_community)}; "
            f"type={value_or_unset(state.property_type)}; "
            f"bedrooms={value_or_unset(bedrooms)}; "
            f"bathrooms={value_or_unset(state.bathrooms)}; "
            f"min_budget_aed={value_or_unset(state.minimum_budget_aed)}; "
            f"max_budget_aed={value_or_unset(state.maximum_budget_aed)}; "
            f"furnishing={value_or_unset(state.furnishing_preference)}; "
            f"ready_or_offplan={value_or_unset(state.ready_or_offplan_preference)}; "
            f"selected_listing_ids={selected_ids}."
            + (
                f" Last demo results: {demo_results}."
                if state.last_demo_results and state.data_scope == "demo"
                else ""
            )
        )

    def _tools_for_request(self, tools: list[Any]) -> tuple[list[Any], str]:
        """Use a successful tool's scope to reduce later schemas safely.

        The first request keeps all tools available so the LLM remains responsible
        for interpreting whether the caller wants demo inventory or historical
        analysis.  A tool scope is narrowed only after application code records a
        successful data operation; no lexical intent classifier is used.
        """

        scope = self.session_data.data_scope if self.session_data is not None else None
        if scope == "demo":
            allowed = DEMO_TOOL_NAMES
            tool_mode = "demo"
        elif scope == "historical":
            allowed = HISTORICAL_TOOL_NAMES
            tool_mode = "historical"
        else:
            return tools, "all"

        scoped_tools = [tool for tool in tools if self._tool_name(tool) in allowed]
        if not scoped_tools:
            return tools, "all"
        return scoped_tools, tool_mode

    @staticmethod
    def _tool_name(tool: Any) -> str | None:
        info = getattr(tool, "info", None)
        name = getattr(info, "name", None)
        if isinstance(name, str):
            return name
        tool_id = getattr(tool, "id", None)
        return tool_id if isinstance(tool_id, str) else None

    @asynccontextmanager
    async def _search_acknowledgement(
        self, context: RunContext[PropertySalesSessionData]
    ) -> AsyncIterator[None]:
        """Offer a cancellable, single acknowledgement only while a lookup waits."""
        with_filler = getattr(context, "with_filler", None)
        speech_id = getattr(getattr(context, "speech_handle", None), "id", None)
        if not callable(with_filler) or not speech_id:
            yield
            return

        phrases = {"en": "Let me check.", "ur": "میں دیکھتی ہوں", "ar": "دعني أتحقق."}

        filler_handle: Any = None

        def acknowledgement(_step: int) -> Any:
            nonlocal filler_handle
            if (
                self._acknowledged_speech_id == speech_id
                or context.speech_handle.interrupted
            ):
                return None
            self._acknowledged_speech_id = speech_id
            language = getattr(context.userdata, "preferred_language", "en")
            filler_handle = context.session.say(
                phrases.get(language, phrases["en"]),
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            if self.latency_recorder is not None:
                self.latency_recorder.record_metric(
                    stage="agent_speech",
                    metric="search_acknowledgement_requested",
                    value=1,
                    unit="event",
                    source="receptionist.search_filler",
                    speech_id=speech_id,
                    labels={
                        "language_code": language,
                        "acknowledgement_speech_id": getattr(filler_handle, "id", None),
                    },
                )
            return filler_handle

        try:
            async with with_filler(acknowledgement, delay=0.15, max_steps=1):
                yield
        finally:
            if filler_handle is not None and not filler_handle.done():
                filler_handle.interrupt()

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
        brief_result_requested: bool = False,
    ) -> dict[str, Any] | ToolResult:
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
        fields preserve existing call preferences. Limit must be between 1 and 5.
        The demo schema has no
        ready/off-plan field. Set brief_result_requested true only when the caller
        wants a simple first option and has not asked for multiple listings,
        specific additional details, comparisons, or a different answer format.
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
                async with self._search_acknowledgement(context):
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
            context.userdata.data_scope = "demo"
            fast_enabled = configured_fast_property_results()
            context.userdata.last_demo_results = (
                [
                    {
                        key: row.get(key)
                        for key in (
                            "listing_id",
                            "property_type",
                            "community",
                            "bedrooms",
                            "bathrooms",
                            "area_sqft",
                            "price_aed",
                            "currency",
                            "price_period",
                            "furnishing",
                            "view_type",
                            "availability_status",
                        )
                    }
                    for row in result.get("results", [])
                    if isinstance(row, dict)
                ][:5]
                if fast_enabled
                else []
            )
            if fast_enabled and brief_result_requested is True:
                language = context.userdata.preferred_language
                spoken = render_demo_result(result, language)
                speech_handle = getattr(context, "speech_handle", None)
                session = getattr(context, "session", None)
                if (
                    spoken
                    and speech_handle
                    and not speech_handle.interrupted
                    and session
                ):
                    caller_revision = context.userdata.caller_activity_revision
                    try:
                        reply_handle = session.say(
                            spoken, allow_interruptions=True, add_to_chat_ctx=True
                        )
                    except Exception:
                        logger.exception("Fast property speech could not be scheduled")
                    else:

                        def cancel_if_interrupted(parent: Any) -> None:
                            if parent.interrupted and not reply_handle.done():
                                reply_handle.interrupt()

                        if reply_handle is not None and callable(
                            getattr(speech_handle, "add_done_callback", None)
                        ):
                            speech_handle.add_done_callback(cancel_if_interrupted)
                        if reply_handle is not None and callable(
                            getattr(reply_handle, "add_done_callback", None)
                        ):

                            def record_reply_failure(handle: Any) -> None:
                                if handle.interrupted or handle.exception() is None:
                                    return
                                logger.error(
                                    "Fast property speech failed after scheduling"
                                )
                                self._record_tool_value(
                                    context,
                                    "fast_property_reply_failed",
                                    1,
                                    "event",
                                    tool_name,
                                    labels={
                                        "reply_speech_id": getattr(handle, "id", None)
                                    },
                                )
                                # A new caller utterance invalidates any recovery.
                                if (
                                    speech_handle.interrupted
                                    or context.userdata.caller_activity_revision
                                    != caller_revision
                                    or getattr(session, "user_state", None)
                                    != "listening"
                                    or getattr(session, "current_speech", None)
                                    not in (None, handle)
                                ):
                                    self._record_tool_value(
                                        context,
                                        "fast_property_recovery_suppressed",
                                        1,
                                        "event",
                                        tool_name,
                                    )
                                    return
                                apologies = {
                                    "en": "Sorry, there was an audio problem. Please ask me again.",
                                    "ur": "معذرت، آواز میں مسئلہ ہوا. براہ کرم دوبارہ پوچھیں",
                                    "ar": "عذراً، حدثت مشكلة في الصوت. يرجى السؤال مرة أخرى.",
                                }
                                try:
                                    session.say(
                                        apologies.get(language, apologies["en"]),
                                        allow_interruptions=True,
                                        add_to_chat_ctx=False,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Fast property recovery speech could not be scheduled"
                                    )
                                else:
                                    self._record_tool_value(
                                        context,
                                        "fast_property_recovery_scheduled",
                                        1,
                                        "event",
                                        tool_name,
                                    )

                            reply_handle.add_done_callback(record_reply_failure)
                        self._record_tool_value(
                            context,
                            "fast_property_reply_scheduled",
                            1,
                            "event",
                            tool_name,
                            labels={
                                "reply_speech_id": getattr(reply_handle, "id", None)
                            },
                        )
                        return ToolResult(result, reply_required=False)
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
                async with self._search_acknowledgement(context):
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
            context.userdata.data_scope = "demo"
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
    async def switch_data_scope(
        self,
        context: RunContext[PropertySalesSessionData],
        data_scope: str,
    ) -> str:
        """Switch between synthetic demo inventory and historical analysis.

        Use this only when the caller explicitly changes data domains. Pass
        exactly "demo" for synthetic sale/rent listings or "historical" for
        historical secondary-sales analysis, then call the relevant data tool.
        """

        normalized_scope = data_scope.strip().casefold()
        if normalized_scope not in {"demo", "historical"}:
            raise ToolError('data_scope must be "demo" or "historical"')
        if normalized_scope == "demo":
            context.userdata.data_scope = "demo"
            return "Demo inventory scope selected. Continue with the requested synthetic listing search."
        context.userdata.data_scope = "historical"
        return "Historical scope selected. Continue with the requested historical sales tool."

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
        result = await self._run_sales_tool(
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
        if isinstance(context.userdata, PropertySalesSessionData):
            context.userdata.data_scope = "historical"
        return result

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
        result = await self._run_sales_tool(
            self.sales_database.market_insights,
            area=area,
            property_type=property_type,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
        if isinstance(context.userdata, PropertySalesSessionData):
            context.userdata.data_scope = "historical"
        return result

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
        result = await self._run_sales_tool(
            self.sales_database.compare_areas,
            area_a=area_a,
            area_b=area_b,
            property_type=property_type,
            bedrooms=bedrooms,
            start_date=start_date,
            end_date=end_date,
        )
        if isinstance(context.userdata, PropertySalesSessionData):
            context.userdata.data_scope = "historical"
        return result
