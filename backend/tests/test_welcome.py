from types import SimpleNamespace

import pytest

from voiceforce_agent.state import PropertySalesSessionData
from voiceforce_agent.welcome import (
    WELCOME_PROMPT,
    LanguageSelectionAgent,
    WelcomeCoordinator,
    normalize_language_selection,
)


class FakeSpeechHandle:
    def __init__(self, error: BaseException | None = None) -> None:
        self._error = error

    async def wait_for_playout(self) -> None:
        return None

    def exception(self) -> BaseException | None:
        return self._error


class FakeSession:
    def __init__(self) -> None:
        self.userdata = PropertySalesSessionData()
        self.spoken: list[str] = []

    def say(self, text: str, **kwargs: object) -> FakeSpeechHandle:
        assert kwargs == {
            "allow_interruptions": False,
            "add_to_chat_ctx": False,
        }
        self.spoken.append(text)
        return FakeSpeechHandle()


class ClosingSession(FakeSession):
    def say(self, text: str, **kwargs: object) -> FakeSpeechHandle:
        raise RuntimeError("AgentSession is closing, cannot use say()")


class FakeRouter:
    def __init__(self) -> None:
        self.languages: list[str] = []
        self.active_agent = None

    def activate_language(self, language: str, **kwargs: object) -> bool:
        self.languages.append(language)
        return True


class RecordingRecorder:
    def __init__(self) -> None:
        self.metrics: list[dict[str, object]] = []

    def record_metric(self, **kwargs: object) -> None:
        self.metrics.append(kwargs)


@pytest.mark.asyncio
async def test_welcome_sequence_is_ordered_and_runs_only_once() -> None:
    session = FakeSession()
    router = FakeRouter()
    recorder = RecordingRecorder()
    statuses: list[dict[str, object]] = []

    async def publish(status: dict[str, object]) -> None:
        statuses.append(status)

    coordinator = WelcomeCoordinator(
        session,
        router,
        recorder=recorder,
        status_publisher=publish,
    )

    assert await coordinator.run() is True
    assert await coordinator.run() is False

    assert session.spoken == [WELCOME_PROMPT]
    assert router.languages == ["en"]
    assert session.userdata.welcome_sequence_started is True
    assert session.userdata.welcome_sequence_completed is True
    assert session.userdata.selection_pending is True
    assert statuses[-1]["phase"] == "listening"
    assert (
        sum(
            metric["metric"] == "welcome_sequence_started"
            for metric in recorder.metrics
        )
        == 1
    )
    assert (
        sum(
            metric["metric"] == "welcome_sequence_completed"
            for metric in recorder.metrics
        )
        == 1
    )


@pytest.mark.asyncio
async def test_welcome_sequence_ends_cleanly_when_session_is_closing() -> None:
    session = ClosingSession()
    recorder = RecordingRecorder()

    result = await WelcomeCoordinator(
        session,
        FakeRouter(),
        recorder=recorder,
    ).run()

    assert result is False
    assert session.userdata.welcome_sequence_started is True
    assert session.userdata.welcome_sequence_completed is False
    assert [metric["metric"] for metric in recorder.metrics] == [
        "welcome_sequence_started",
        "welcome_sequence_cancelled",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("English", "en"),
        ("English please", "en"),
        ("Urdu", "ur"),
        ("Urdu mein", "ur"),
        ("اردو", "ur"),
        ("hi-IN", "ur"),
        ("Arabic please", "ar"),
        ("العربية", "ar"),
    ],
)
def test_language_selection_aliases(value: str, expected: str) -> None:
    assert normalize_language_selection(value) == expected


@pytest.mark.parametrize("value", [None, "", "English and Urdu", "French"])
def test_ambiguous_or_unsupported_language_selection_is_not_defaulted(
    value: object,
) -> None:
    assert normalize_language_selection(value) is None


@pytest.mark.asyncio
async def test_selector_tool_preserves_state_and_returns_receptionist_handoff() -> None:
    created_contexts = []
    statuses: list[dict[str, object]] = []

    class Router:
        def __init__(self) -> None:
            self.active_agent = None

        def activate_language(self, language: str, **kwargs: object) -> bool:
            assert language == "ur"
            return True

        def set_active_agent(self, agent: object) -> None:
            self.active_agent = agent

    router = Router()

    def make_receptionist(chat_ctx: object) -> object:
        created_contexts.append(chat_ctx)
        return SimpleNamespace(language_router=None)

    async def publish(status: dict[str, object]) -> None:
        statuses.append(status)

    selector = LanguageSelectionAgent(
        receptionist_factory=make_receptionist,
        status_publisher=publish,
    )
    selector.language_router = router  # type: ignore[assignment]
    userdata = PropertySalesSessionData(
        welcome_sequence_completed=True,
        selection_pending=True,
    )
    context = SimpleNamespace(userdata=userdata)

    result = await selector.select_language._func(selector, context, "Urdu")

    assert isinstance(result, tuple)
    receptionist, confirmation = result
    assert receptionist.language_router is router
    assert "اردو" in confirmation
    assert userdata.selected_language == "ur"
    assert userdata.preferred_language == "ur"
    assert userdata.selection_pending is False
    assert userdata.active_agent == "receptionist"
    assert userdata.selection_attempts == 1
    assert len(created_contexts) == 1
    assert statuses == [
        {"phase": "selected", "language": "ur", "active_agent": "receptionist"}
    ]
