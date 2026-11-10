from voiceforce_agent.config import (
    build_llm,
    build_stt,
    build_tts,
    build_tts_for_language,
    normalize_language_code,
    resolve_voice_route,
)
from voiceforce_agent.receptionist import Receptionist


def test_inference_models_are_configured() -> None:
    stt = build_stt()
    llm = build_llm()
    tts = build_tts()

    assert (stt.model, stt.provider) == ("assemblyai/universal-3-6-pro", "livekit")
    assert stt._opts.language.__class__.__name__ == "NotGiven"
    assert stt._opts.extra_kwargs == {
        "language_detection": True,
        "language_codes": ["en", "ur", "ar"],
        "mode": "balanced",
    }
    assert (llm.model, llm.provider) == ("openai/gpt-5-mini", "livekit")
    assert (tts.model, tts.provider) == ("fishaudio/s2.1-pro", "livekit")


def test_inworld_tts_uses_deployment_selected_language_voice(monkeypatch) -> None:
    monkeypatch.setenv("VOICEFORCE_INWORLD_URDU_VOICE", "urdu-voice")
    monkeypatch.setenv("VOICEFORCE_INWORLD_ARABIC_VOICE", "arabic-voice")

    urdu = build_tts_for_language("ur")
    arabic = build_tts_for_language("ar")

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


def test_multilingual_voice_is_required_only_when_that_language_is_selected(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VOICEFORCE_INWORLD_URDU_VOICE", raising=False)

    build_tts()

    try:
        build_tts_for_language("ur")
    except RuntimeError as error:
        assert "VOICEFORCE_INWORLD_URDU_VOICE" in str(error)
    else:
        raise AssertionError("Urdu voice configuration should be required")


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
