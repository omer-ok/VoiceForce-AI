from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from livekit.agents import Agent, ChatContext, ModelSettings
from livekit.agents.llm import ToolError

from voiceforce_agent.receptionist import (
    DEMO_TOOL_NAMES,
    HISTORICAL_TOOL_NAMES,
    Receptionist,
)
from voiceforce_agent.state import PropertySalesSessionData


async def _capture_llm_request(
    monkeypatch, receptionist: Receptionist, chat_ctx: ChatContext
) -> dict[str, object]:
    captured: dict[str, object] = {}

    async def fake_llm_node(agent, request_ctx, tools, model_settings):
        del agent, model_settings
        captured["context"] = request_ctx
        captured["tools"] = tools
        if False:
            yield None

    monkeypatch.setattr(Agent.default, "llm_node", staticmethod(fake_llm_node))
    async for _ in receptionist.llm_node(
        chat_ctx,
        receptionist.tools,
        ModelSettings(),
    ):
        pass
    return captured


def _tool_names(tools: object) -> set[str]:
    return {tool.id for tool in tools}  # type: ignore[union-attr]


def _long_context() -> ChatContext:
    chat_ctx = ChatContext.empty()
    chat_ctx.add_message(role="system", content="system instructions")
    for index in range(20):
        chat_ctx.add_message(role="user", content=f"caller turn {index}")
        chat_ctx.add_message(role="assistant", content=f"reply turn {index}")
    return chat_ctx


async def test_llm_request_trims_context_and_scopes_demo_tools(monkeypatch) -> None:
    state = PropertySalesSessionData(
        data_scope="demo",
        transaction_intent="rent",
        preferred_community="Dubai Marina",
        selected_listing_ids=["demo-rent-001"],
    )
    receptionist = Receptionist(session_data=state)

    captured = await _capture_llm_request(monkeypatch, receptionist, _long_context())

    request_ctx = captured["context"]
    assert len(request_ctx.items) <= 14  # type: ignore[union-attr]
    assert any(
        "Internal call state" in str(item.content)
        for item in request_ctx.messages()  # type: ignore[union-attr]
    )
    assert _tool_names(captured["tools"]) == DEMO_TOOL_NAMES


async def test_llm_request_scopes_historical_tools_without_keyword_routing(
    monkeypatch,
) -> None:
    state = PropertySalesSessionData(data_scope="historical")
    receptionist = Receptionist(session_data=state)

    captured = await _capture_llm_request(monkeypatch, receptionist, _long_context())

    assert _tool_names(captured["tools"]) == HISTORICAL_TOOL_NAMES


async def test_llm_request_keeps_all_tools_before_a_successful_data_call(
    monkeypatch,
) -> None:
    state = PropertySalesSessionData()
    receptionist = Receptionist(session_data=state)

    captured = await _capture_llm_request(monkeypatch, receptionist, _long_context())

    assert _tool_names(captured["tools"]) == _tool_names(receptionist.tools)


@pytest.mark.asyncio
async def test_scope_switch_is_model_driven_and_validated() -> None:
    state = PropertySalesSessionData(data_scope="demo")
    context = SimpleNamespace(userdata=state)
    receptionist = Receptionist(session_data=state)

    result = await Receptionist.switch_data_scope._func(
        receptionist,
        context,
        "historical",
    )

    assert state.data_scope == "historical"
    assert "Historical scope selected" in result

    with pytest.raises(ToolError, match="data_scope"):
        await Receptionist.switch_data_scope._func(
            receptionist,
            context,
            "unknown",
        )


@pytest.mark.parametrize(
    "language,expected",
    [("en", "Let me check."), ("ur", "میں دیکھتی ہوں"), ("ar", "دعني أتحقق.")],
)
async def test_search_acknowledgement_is_localized_and_cancelled(
    language, expected
) -> None:
    played = []
    interrupted = []
    handle = SimpleNamespace(
        done=lambda: False, interrupt=lambda: interrupted.append(True)
    )

    def say(text, **kwargs):
        played.append((text, kwargs))
        return handle

    @asynccontextmanager
    async def filler(source, **kwargs):
        assert kwargs == {"delay": 0.15, "max_steps": 1}
        assert source(0) is handle
        yield

    context = SimpleNamespace(
        userdata=SimpleNamespace(preferred_language=language),
        speech_handle=SimpleNamespace(id="turn-1", interrupted=False),
        session=SimpleNamespace(say=say),
        with_filler=filler,
    )
    async with Receptionist()._search_acknowledgement(context):
        assert interrupted == []
    assert played == [
        (expected, {"allow_interruptions": True, "add_to_chat_ctx": False})
    ]
    assert interrupted == [True]


async def test_search_acknowledgement_skips_interrupted_or_repeated_turns() -> None:
    @asynccontextmanager
    async def filler(source, **_kwargs):
        assert source(0) is None
        yield

    context = SimpleNamespace(
        userdata=SimpleNamespace(preferred_language="en"),
        speech_handle=SimpleNamespace(id="turn-1", interrupted=True),
        with_filler=filler,
    )
    receptionist = Receptionist()
    async with receptionist._search_acknowledgement(context):
        pass
    context.speech_handle.interrupted = False
    receptionist._acknowledged_speech_id = "turn-1"
    async with receptionist._search_acknowledgement(context):
        pass
