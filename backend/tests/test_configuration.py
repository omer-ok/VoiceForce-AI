import pytest

import voiceforce_agent.config as config
from voiceforce_agent.config import (
    build_llm,
    build_stt,
    build_tts,
    build_tts_for_language,
    build_turn_handling,
    build_vad,
    configured_benchmark_labels,
    configured_fast_property_results,
    configured_llm,
    configured_preemptive_generation,
    normalize_language_code,
    resolve_voice_route,
)
from voiceforce_agent.receptionist import RECEPTIONIST_SYSTEM_PROMPT, Receptionist


def test_inference_models_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_LLM_MODEL", "openai/gpt-5-mini")
    monkeypatch.setenv("VOICEFORCE_LLM_REASONING_EFFORT", "low")
    monkeypatch.setenv("VOICEFORCE_LLM_MAX_COMPLETION_TOKENS", "256")
    monkeypatch.setenv("VOICEFORCE_INWORLD_MODEL", "inworld/inworld-tts-2-flash")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ENGLISH_VOICE", "Simon")
    stt = build_stt()
    vad = build_vad()
    turn_handling = build_turn_handling()
    llm = build_llm()
    tts = build_tts()

    assert (stt.model, stt.provider) == ("assemblyai/universal-3-6-pro", "livekit")
    assert stt._opts.language.__class__.__name__ == "NotGiven"
    assert stt._opts.extra_kwargs == {
        "language_detection": True,
        "language_codes": ["en", "ur", "ar"],
        "mode": "min_latency",
        "min_turn_silence": 100,
        "max_turn_silence": 1000,
        "vad_threshold": 0.3,
    }
    assert vad.model == "silero"
    assert vad._opts.activation_threshold == 0.3
    assert turn_handling == {
        "turn_detection": "stt",
        "endpointing": {"mode": "fixed", "min_delay": 0.0},
        "preemptive_generation": {
            "enabled": True,
            "preemptive_tts": True,
            "max_speech_duration": 8.0,
            "max_retries": 2,
        },
    }
    assert (llm.model, llm.provider) == ("openai/gpt-5-mini", "livekit")
    assert llm._opts.extra_kwargs == {
        "reasoning_effort": "low",
        "max_completion_tokens": 256,
    }
    assert (tts.model, tts.provider) == ("inworld/inworld-tts-2-flash", "livekit")
    assert (tts._opts.voice, tts._opts.language) == ("Simon", "en")


def test_preemptive_generation_can_be_rolled_back_and_tuned(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_PREEMPTIVE_TTS", "false")
    monkeypatch.setenv("VOICEFORCE_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS", "12")
    monkeypatch.setenv("VOICEFORCE_PREEMPTIVE_TTS_MAX_RETRIES", "1")

    configuration = configured_preemptive_generation()

    assert configuration.enabled is True
    assert configuration.preemptive_tts is False
    assert configuration.max_speech_duration == 12.0
    assert configuration.max_retries == 1


def test_fast_property_candidate_defaults_off_and_validates_override(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VOICEFORCE_FAST_PROPERTY_RESULTS", raising=False)
    assert configured_fast_property_results() is False
    monkeypatch.setenv("VOICEFORCE_FAST_PROPERTY_RESULTS", "true")
    assert configured_fast_property_results() is True
    monkeypatch.setenv("VOICEFORCE_FAST_PROPERTY_RESULTS", "invalid")
    with pytest.raises(RuntimeError, match="VOICEFORCE_FAST_PROPERTY_RESULTS"):
        configured_fast_property_results()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("VOICEFORCE_PREEMPTIVE_TTS", "maybe"),
        ("VOICEFORCE_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS", "not-a-number"),
        ("VOICEFORCE_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS", "0"),
        ("VOICEFORCE_PREEMPTIVE_TTS_MAX_RETRIES", "not-an-integer"),
        ("VOICEFORCE_PREEMPTIVE_TTS_MAX_RETRIES", "11"),
    ],
)
def test_invalid_preemptive_generation_configuration_fails(
    monkeypatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(RuntimeError, match=variable):
        configured_preemptive_generation()


@pytest.mark.parametrize(
    ("model", "reasoning_effort"),
    [
        ("openai/gpt-5-mini", "low"),
        ("openai/gpt-5.6-terra", "none"),
        ("openai/gpt-5.6-luna", "none"),
    ],
)
def test_llm_configuration_supports_benchmark_candidates(
    monkeypatch, model: str, reasoning_effort: str
) -> None:
    monkeypatch.setenv("VOICEFORCE_LLM_MODEL", model)
    monkeypatch.setenv("VOICEFORCE_LLM_REASONING_EFFORT", reasoning_effort)
    monkeypatch.setenv("VOICEFORCE_LLM_MAX_COMPLETION_TOKENS", "256")

    configuration = configured_llm()
    llm = build_llm(configuration)

    assert configuration.model == model
    assert configuration.reasoning_effort == reasoning_effort
    assert configuration.max_completion_tokens == 256
    assert (llm.model, llm.provider) == (model, "livekit")
    assert llm._opts.extra_kwargs == {
        "reasoning_effort": reasoning_effort,
        "max_completion_tokens": 256,
    }


@pytest.mark.parametrize("model", ["openai/gpt-5.6-terra", "openai/gpt-5.6-luna"])
def test_llm_candidates_support_short_voice_completion(monkeypatch, model: str) -> None:
    monkeypatch.setenv("VOICEFORCE_LLM_MODEL", model)
    monkeypatch.setenv("VOICEFORCE_LLM_REASONING_EFFORT", "none")
    monkeypatch.setenv("VOICEFORCE_LLM_MAX_COMPLETION_TOKENS", "160")

    configuration = configured_llm()
    assert configuration.model == model
    assert configuration.reasoning_effort == "none"
    assert build_llm(configuration)._opts.extra_kwargs["max_completion_tokens"] == 160


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        (
            "VOICEFORCE_LLM_MODEL",
            "openai/not-a-real-model",
            "VOICEFORCE_LLM_MODEL",
        ),
        (
            "VOICEFORCE_LLM_REASONING_EFFORT",
            "ultra",
            "VOICEFORCE_LLM_REASONING_EFFORT",
        ),
        (
            "VOICEFORCE_LLM_MAX_COMPLETION_TOKENS",
            "not-an-integer",
            "VOICEFORCE_LLM_MAX_COMPLETION_TOKENS",
        ),
        (
            "VOICEFORCE_LLM_MAX_COMPLETION_TOKENS",
            "32",
            "VOICEFORCE_LLM_MAX_COMPLETION_TOKENS",
        ),
    ],
)
def test_invalid_llm_configuration_fails_before_provider_use(
    monkeypatch, variable: str, value: str, expected: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(RuntimeError, match=expected):
        configured_llm()


def test_optional_benchmark_labels_are_explicit_and_privacy_safe(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_BENCHMARK_RUN_ID", "terra-none-warm-01")
    monkeypatch.setenv("VOICEFORCE_BENCHMARK_SCENARIO", "one_tool_property_search")
    monkeypatch.setenv("VOICEFORCE_BENCHMARK_COLD_WARM", "warm")
    monkeypatch.setenv("VOICEFORCE_BENCHMARK_LANGUAGE", "en")
    monkeypatch.setenv("VOICEFORCE_BENCHMARK_AUDIO_MODE", "true")

    assert configured_benchmark_labels() == {
        "benchmark_run_id": "terra-none-warm-01",
        "benchmark_scenario": "one_tool_property_search",
        "benchmark_cold_warm": "warm",
        "benchmark_language": "en",
        "benchmark_audio_mode": "true",
    }


def test_inworld_tts_uses_deployment_selected_language_voice(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_MODEL", "inworld/inworld-tts-2-flash")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ENGLISH_VOICE", "Simon")
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "urdu-voice")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ARABIC_VOICE", "arabic-voice")

    english = build_tts_for_language("en")
    urdu = build_tts_for_language("ur")
    arabic = build_tts_for_language("ar")

    assert (english.model, english._opts.voice, english._opts.language) == (
        "inworld/inworld-tts-2-flash",
        "Simon",
        "en",
    )
    assert (urdu.model, urdu._opts.voice, urdu._opts.language) == (
        "inworld/inworld-tts-2-flash",
        "urdu-voice",
        "ur-PK",
    )
    assert (arabic.model, arabic._opts.voice, arabic._opts.language) == (
        "inworld/inworld-tts-2-flash",
        "arabic-voice",
        "ar-SA",
    )


def test_hindi_detection_is_an_explicit_urdu_voice_alias(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_MODEL", "inworld/inworld-tts-2-flash")
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")

    assert normalize_language_code("hi") == "ur"
    assert normalize_language_code("hi-IN") == "ur"
    route = resolve_voice_route("hi-IN")

    assert route is not None
    assert route.detected_language == "hi-IN"
    assert route.effective_language == "ur"
    assert route.provider == "inworld"
    assert route.model == "inworld/inworld-tts-2-flash"
    assert route.voice == "Aarav"
    assert route.locale == "ur-PK"
    assert route.alias_applied is True


def test_all_routes_construct_inworld_tts_without_provider_calls(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_MODEL", "inworld/inworld-tts-2-flash")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ENGLISH_VOICE", "Simon")
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "Aarav")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ARABIC_VOICE", "Omar")
    created: list[dict[str, str]] = []

    class FakeTTS:
        provider = "livekit"

        def __init__(self, **kwargs: str) -> None:
            created.append(kwargs)
            self.model = kwargs["model"]
            self._opts = type(
                "Options",
                (),
                {
                    "voice": kwargs["voice"],
                    "language": kwargs["language"],
                },
            )()

    monkeypatch.setattr(config.inference, "TTS", FakeTTS)

    for language in ("en", "ur", "ar"):
        build_tts_for_language(language)  # type: ignore[arg-type]

    assert created == [
        {
            "model": "inworld/inworld-tts-2-flash",
            "voice": "Simon",
            "language": "en",
        },
        {
            "model": "inworld/inworld-tts-2-flash",
            "voice": "Aarav",
            "language": "ur-PK",
        },
        {
            "model": "inworld/inworld-tts-2-flash",
            "voice": "Omar",
            "language": "ar-SA",
        },
    ]


def test_multilingual_voice_is_required_only_when_that_language_is_selected(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_ENGLISH_VOICE", "Simon")
    monkeypatch.delenv("VOICEFORCE_INWORLD_URDU_VOICE", raising=False)

    build_tts()

    try:
        build_tts_for_language("ur")
    except RuntimeError as error:
        assert "VOICEFORCE_INWORLD_URDU_VOICE" in str(error)
    else:
        raise AssertionError("Urdu voice configuration should be required")


def test_english_voice_is_required_when_english_is_selected(monkeypatch) -> None:
    monkeypatch.delenv("VOICEFORCE_INWORLD_ENGLISH_VOICE", raising=False)

    try:
        build_tts_for_language("en")
    except RuntimeError as error:
        assert "VOICEFORCE_INWORLD_ENGLISH_VOICE" in str(error)
    else:
        raise AssertionError("English voice configuration should be required")


def test_direct_inworld_plugin_model_identifier_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_MODEL", "inworld-tts-2-flash")

    try:
        resolve_voice_route("en")
    except RuntimeError as error:
        assert "LiveKit Inference" in str(error)
    else:
        raise AssertionError("Unqualified direct-plugin model ID should be rejected")


def test_invalid_tts_language_is_rejected() -> None:
    try:
        build_tts_for_language("xx")  # type: ignore[arg-type]
    except ValueError as error:
        assert "unsupported TTS language" in str(error)
    else:
        raise AssertionError("Unsupported TTS language should be rejected")


def test_receptionist_is_grounded_for_initial_milestone() -> None:
    instructions = Receptionist().instructions

    assert "Do not invent property availability" in instructions
    assert "Historical sales tools are available" in instructions
    assert "cannot verify live availability" in instructions
    assert "Never generate Hindi or Devanagari response text" in instructions


def test_receptionist_prompt_is_compact_without_dropping_required_rules() -> None:
    assert len(RECEPTIONIST_SYSTEM_PROMPT) < 4_000
    assert len(RECEPTIONIST_SYSTEM_PROMPT.split()) < 410
    for required_rule in (
        "search_demo_properties",
        "get_inventory_summary",
        "capture_customer_lead",
        "caller explicitly agrees to save",
        "confirms their name and",
        "phone number",
        "simulated",
        "not verified",
        "USD, not AED",
        "ready/off-plan",
    ):
        assert required_rule in RECEPTIONIST_SYSTEM_PROMPT
