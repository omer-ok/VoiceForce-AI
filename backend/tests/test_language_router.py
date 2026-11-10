from types import SimpleNamespace

import pytest

from voiceforce_agent import language_router
from voiceforce_agent.config import resolve_voice_route
from voiceforce_agent.language_router import MultilingualTTSRouter
from voiceforce_agent.state import PropertySalesSessionData


class FakeTTS:
    provider = "livekit"

    def __init__(self, model: str, language: str, voice: str) -> None:
        self.model = model
        self.language = language
        self._opts = SimpleNamespace(voice=voice, language=language)


class FakeAgent:
    def __init__(self) -> None:
        self.updates: list[FakeTTS] = []

    def update_options(self, *, tts: FakeTTS) -> None:
        self.updates.append(tts)


class RecordingRecorder:
    def __init__(self) -> None:
        self.metrics: list[dict[str, object]] = []
        self.missing: list[dict[str, object]] = []

    def record_metric(self, **kwargs: object) -> None:
        self.metrics.append(kwargs)

    def record_missing(self, **kwargs: object) -> None:
        self.missing.append(kwargs)

    def set_effective_voice_language(
        self, language: str, *, turn_id: str | None = None
    ) -> None:
        self.metrics.append(
            {
                "metric": "effective_voice_language",
                "language": language,
                "turn_id": turn_id,
            }
        )


def fake_tts_for_language(language: str) -> FakeTTS:
    route = resolve_voice_route(language)
    assert route is not None
    return FakeTTS(route.model, route.locale, route.voice)


def test_language_tags_update_session_state_and_switch_tts(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    created: list[FakeTTS] = []

    def fake_build(language: str) -> FakeTTS:
        tts = fake_tts_for_language(language)
        created.append(tts)
        return tts

    monkeypatch.setattr(language_router, "build_tts_for_language", fake_build)
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    english = fake_tts_for_language("en")
    router = MultilingualTTSRouter(agent, session, english_tts=english)

    router.on_user_input_transcribed(
        SimpleNamespace(
            language="ur-PK",
            language_confidence=0.91,
            is_final=True,
            item_id="turn-1",
        )
    )

    assert session.userdata.preferred_language == "ur"
    assert session.userdata.language_confidence == 0.91
    assert router.active_language == "ur"
    assert agent.updates == [created[0]]
    assert created[0].language == "ur-PK"
    assert created[0]._opts.voice == "Aarav"


@pytest.mark.parametrize("detected_language", ["ur", "ur-PK", "hi", "hi-IN"])
def test_urdu_and_hindi_detection_selects_aarav_urdu_route(
    monkeypatch, detected_language: str
) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        lambda language: fake_tts_for_language(language),
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    router = MultilingualTTSRouter(
        agent,
        session,
        english_tts=fake_tts_for_language("en"),
    )

    router.on_user_input_transcribed(
        SimpleNamespace(
            language=detected_language,
            transcript="میں دبئی میں پراپرٹی تلاش کر رہا ہوں",
            is_final=True,
            item_id="turn-urdu",
        )
    )

    assert router.active_language == "ur"
    assert session.userdata.preferred_language == "ur"
    assert agent.updates[-1]._opts.voice == "Aarav"
    assert agent.updates[-1]._opts.language == "ur-PK"


def test_language_switches_back_to_cached_english_tts(monkeypatch) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    english = fake_tts_for_language("en")
    router = MultilingualTTSRouter(agent, session, english_tts=english)

    router.on_user_input_transcribed(
        SimpleNamespace(language="ar-SA", is_final=True, item_id="turn-1")
    )
    router.on_user_input_transcribed(
        SimpleNamespace(language="en-US", is_final=True, item_id="turn-2")
    )

    assert session.userdata.preferred_language == "en"
    assert router.active_language == "en"
    assert agent.updates[-1] is english


def test_interim_language_metadata_does_not_override_completed_urdu_route(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    router = MultilingualTTSRouter(
        agent,
        session,
        english_tts=fake_tts_for_language("en"),
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="ur", is_final=True, item_id="turn-1")
    )
    router.on_user_input_transcribed(
        SimpleNamespace(language="en", is_final=False, item_id="turn-1")
    )

    assert router.active_language == "ur"
    assert session.userdata.preferred_language == "ur"
    assert len(agent.updates) == 1


def test_language_choice_stage_records_detection_without_switching_voice(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    agent = FakeAgent()
    session = SimpleNamespace(
        userdata=PropertySalesSessionData(selection_pending=True),
    )
    router = MultilingualTTSRouter(
        agent,
        session,
        english_tts=fake_tts_for_language("en"),
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="en", is_final=True, item_id="choice-1")
    )

    assert router.active_language == "en"
    assert session.userdata.preferred_language == "en"
    assert agent.updates == []


def test_missing_language_metadata_preserves_established_route(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    agent = FakeAgent()
    router = MultilingualTTSRouter(
        agent,
        session,
        english_tts=fake_tts_for_language("en"),
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="ur-PK", is_final=True, item_id="turn-1")
    )
    router.on_user_input_transcribed(
        SimpleNamespace(language=None, is_final=True, item_id="turn-2")
    )

    assert router.active_language == "ur"
    assert session.userdata.preferred_language == "ur"
    assert len(agent.updates) == 1


def test_language_switches_english_urdu_arabic_urdu(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ARABIC_VOICE", "Omar")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    english = fake_tts_for_language("en")
    router = MultilingualTTSRouter(agent, session, english_tts=english)

    for language in ("en", "ur", "ar", "ur"):
        router.on_user_input_transcribed(
            SimpleNamespace(
                language=language, is_final=True, item_id=f"turn-{language}"
            )
        )

    assert [tts._opts.language for tts in agent.updates] == [
        "ur-PK",
        "ar-SA",
        "ur-PK",
    ]
    assert agent.updates[0] is agent.updates[-1]
    assert agent.updates[1]._opts.voice == "Omar"
    assert router.active_language == "ur"


def test_hindi_alias_preserves_detected_language_separately_from_voice_route(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    recorder = RecordingRecorder()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    router = MultilingualTTSRouter(
        FakeAgent(),
        session,
        english_tts=fake_tts_for_language("en"),
        recorder=recorder,
    )
    event = SimpleNamespace(
        language="hi-IN",
        transcript="میں دبئی میں گھر تلاش کر رہا ہوں",
        is_final=True,
        item_id="turn-hi-alias",
    )

    router.on_user_input_transcribed(event)

    detected = next(
        metric
        for metric in recorder.metrics
        if metric.get("metric") == "language_detected"
    )
    assert detected["labels"]["detected_language"] == "hi-IN"
    assert detected["labels"]["effective_voice_language"] == "ur"
    assert detected["labels"]["alias_applied"] is True
    assert session.userdata.last_detected_language == "hi-IN"
    assert event.transcript.startswith("میں")
    assert all("transcript" not in metric for metric in recorder.metrics)


def test_unsupported_language_does_not_change_existing_route(monkeypatch) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    english = fake_tts_for_language("en")
    router = MultilingualTTSRouter(agent, session, english_tts=english)

    router.on_user_input_transcribed(
        SimpleNamespace(language="fr-FR", is_final=True, item_id="turn-1")
    )

    assert session.userdata.preferred_language == "en"
    assert router.active_language == "en"
    assert agent.updates == []


def test_missing_language_voice_keeps_current_route(monkeypatch) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        lambda language: (_ for _ in ()).throw(RuntimeError("missing voice")),
    )
    agent = FakeAgent()
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    english = fake_tts_for_language("en")
    router = MultilingualTTSRouter(agent, session, english_tts=english)

    router.on_user_input_transcribed(
        SimpleNamespace(language="ur", is_final=True, item_id="turn-1")
    )

    assert session.userdata.preferred_language == "en"
    assert router.active_language == "en"
    assert agent.updates == []


def test_switch_duration_and_missing_detection_latency_are_recorded(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )
    recorder = RecordingRecorder()
    router = MultilingualTTSRouter(
        FakeAgent(),
        SimpleNamespace(userdata=PropertySalesSessionData()),
        english_tts=fake_tts_for_language("en"),
        recorder=recorder,
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="ur", is_final=True, item_id="turn-1")
    )

    assert any(
        metric["metric"] == "tts_provider_switch_duration"
        and metric["labels"]["status"] == "ok"
        for metric in recorder.metrics
    )
    assert any(
        missing["metric"] == "language_detection_latency"
        for missing in recorder.missing
    )


def test_failed_provider_switch_is_recorded_without_changing_active_language(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        fake_tts_for_language,
    )

    class FailingAgent(FakeAgent):
        def update_options(self, *, tts: FakeTTS) -> None:
            raise RuntimeError("provider update failed")

    recorder = RecordingRecorder()
    agent = FailingAgent()
    router = MultilingualTTSRouter(
        agent,
        SimpleNamespace(userdata=PropertySalesSessionData()),
        english_tts=fake_tts_for_language("en"),
        recorder=recorder,
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="ar", is_final=True, item_id="turn-1")
    )

    assert router.active_language == "en"
    assert any(
        metric["metric"] == "tts_provider_switch_failed" for metric in recorder.metrics
    )
    assert any(
        metric["metric"] == "tts_provider_switch_duration"
        and metric["labels"]["status"] == "failed"
        for metric in recorder.metrics
    )


@pytest.mark.asyncio
async def test_failed_urdu_route_refuses_fish_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        language_router,
        "build_tts_for_language",
        lambda language: (_ for _ in ()).throw(RuntimeError("missing Aarav")),
    )
    session = SimpleNamespace(userdata=PropertySalesSessionData())
    router = MultilingualTTSRouter(
        FakeAgent(),
        session,
        english_tts=fake_tts_for_language("en"),
    )

    router.on_user_input_transcribed(
        SimpleNamespace(language="hi", is_final=True, item_id="turn-1")
    )

    with pytest.raises(RuntimeError, match="refusing to fall back"):
        async for _ in router.tts_node(aiter_text(), SimpleNamespace()):
            pass


@pytest.mark.asyncio
async def test_tts_provider_failure_is_recorded_and_re_raised(monkeypatch) -> None:
    async def failing_tts_node(agent, text, model_settings):
        raise RuntimeError("synthesis failed")
        yield  # pragma: no cover

    monkeypatch.setattr(
        language_router.Agent.default,
        "tts_node",
        staticmethod(failing_tts_node),
    )
    recorder = RecordingRecorder()
    router = MultilingualTTSRouter(
        FakeAgent(),
        SimpleNamespace(userdata=PropertySalesSessionData()),
        english_tts=fake_tts_for_language("en"),
        recorder=recorder,
    )

    with pytest.raises(RuntimeError, match="synthesis failed"):
        async for _ in router.tts_node(aiter_text(), SimpleNamespace()):
            pass

    assert any(
        metric["metric"] == "tts_synthesis_failed" for metric in recorder.metrics
    )
    assert any(metric["metric"] == "tts_provider_error" for metric in recorder.metrics)


async def aiter_text():
    yield "hello"
