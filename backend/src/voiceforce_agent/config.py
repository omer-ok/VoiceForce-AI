import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from livekit.agents import TurnHandlingOptions, inference

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPOSITORY_ROOT / ".env.local")

SupportedLanguage = Literal["en", "ur", "ar"]
DetectedLanguage = Literal["en", "ur", "hi", "ar"]

ENGLISH_LANGUAGE: SupportedLanguage = "en"
URDU_LANGUAGE: SupportedLanguage = "ur"
ARABIC_LANGUAGE: SupportedLanguage = "ar"
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {ENGLISH_LANGUAGE, URDU_LANGUAGE, ARABIC_LANGUAGE}
)
DETECTED_LANGUAGE_BASES: frozenset[str] = frozenset(
    {ENGLISH_LANGUAGE, URDU_LANGUAGE, "hi", ARABIC_LANGUAGE}
)

DEFAULT_INWORLD_TTS_MODEL = "inworld/inworld-tts-2-flash"
# This is the LiveKit Inference model ID. The direct Inworld plugin uses a
# different, unqualified identifier and must not be mixed into this path.
INWORLD_TTS_MODEL_ENV = "VOICEFORCE_INWORLD_MODEL"
ENGLISH_TTS_VOICE_ENV = "VOICEFORCE_INWORLD_ENGLISH_VOICE"
URDU_TTS_VOICE_ENV = "VOICEFORCE_INWORLD_URDU_VOICE"
ARABIC_TTS_VOICE_ENV = "VOICEFORCE_INWORLD_ARABIC_VOICE"
ENGLISH_TTS_LOCALE = "en"
URDU_TTS_LOCALE = "ur-PK"
ARABIC_TTS_LOCALE = "ar-SA"

STT_MODEL = "assemblyai/universal-3-6-pro"
STT_MODE = "min_latency"
STT_MIN_TURN_SILENCE_MS = 100
STT_MAX_TURN_SILENCE_MS = 1_000
STT_VAD_THRESHOLD = 0.3
TURN_DETECTION_MODE = "stt"
ENDPOINTING_MODE = "fixed"
ENDPOINTING_MIN_DELAY_SECONDS = 0.0
DEFAULT_PREEMPTIVE_TTS = True
DEFAULT_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS = 8.0
DEFAULT_PREEMPTIVE_TTS_MAX_RETRIES = 2
PREEMPTIVE_TTS_ENV = "VOICEFORCE_PREEMPTIVE_TTS"
PREEMPTIVE_TTS_MAX_SPEECH_SECONDS_ENV = "VOICEFORCE_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS"
PREEMPTIVE_TTS_MAX_RETRIES_ENV = "VOICEFORCE_PREEMPTIVE_TTS_MAX_RETRIES"
FAST_PROPERTY_RESULTS_ENV = "VOICEFORCE_FAST_PROPERTY_RESULTS"

DEFAULT_LLM_MODEL = "openai/gpt-5-mini"
DEFAULT_LLM_REASONING_EFFORT = "low"
DEFAULT_LLM_MAX_COMPLETION_TOKENS = 256
LLM_MODEL_ENV = "VOICEFORCE_LLM_MODEL"
LLM_REASONING_EFFORT_ENV = "VOICEFORCE_LLM_REASONING_EFFORT"
LLM_MAX_COMPLETION_TOKENS_ENV = "VOICEFORCE_LLM_MAX_COMPLETION_TOKENS"
SUPPORTED_LLM_MODELS: frozenset[str] = frozenset(
    {
        "openai/gpt-5-mini",
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
    }
)
SUPPORTED_LLM_REASONING_EFFORTS: frozenset[str] = frozenset(
    {"none", "low", "medium", "high", "xhigh", "max"}
)
LLM_MAX_COMPLETION_TOKENS_MIN = 64
LLM_MAX_COMPLETION_TOKENS_MAX = 4_096
_BENCHMARK_LABEL_ENV_VARS: tuple[tuple[str, str], ...] = (
    ("VOICEFORCE_BENCHMARK_RUN_ID", "benchmark_run_id"),
    ("VOICEFORCE_BENCHMARK_SCENARIO", "benchmark_scenario"),
    ("VOICEFORCE_BENCHMARK_COLD_WARM", "benchmark_cold_warm"),
    ("VOICEFORCE_BENCHMARK_LANGUAGE", "benchmark_language"),
    ("VOICEFORCE_BENCHMARK_AUDIO_MODE", "benchmark_audio_mode"),
)


@dataclass(frozen=True)
class LLMConfiguration:
    """Validated LiveKit Inference settings for the conversational LLM."""

    model: str
    reasoning_effort: str
    max_completion_tokens: int


@dataclass(frozen=True)
class PreemptiveGenerationConfiguration:
    """Validated bounded speculative-generation settings."""

    enabled: bool
    preemptive_tts: bool
    max_speech_duration: float
    max_retries: int


@dataclass(frozen=True)
class VoiceRoute:
    """The observable TTS decision for one detected language tag."""

    detected_language: str
    effective_language: SupportedLanguage
    provider: Literal["inworld"]
    model: str
    voice: str
    locale: str
    alias_applied: bool


def validate_environment() -> None:
    """Fail clearly when the shared root environment is missing LiveKit settings."""

    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required LiveKit environment variables: {names}")

    configured_llm()
    configured_preemptive_generation()
    configured_fast_property_results()
    _configured_inworld_model()


def build_stt() -> inference.STT:
    """Build multilingual AssemblyAI Universal-3.6 Pro STT.

    Universal-3.6 Pro performs language detection and code-switching when no
    fixed language is supplied.  Use the provider's latency preset and let
    AssemblyAI own end-of-turn detection for this STT pipeline.
    """

    return inference.STT(
        model=STT_MODEL,
        extra_kwargs={
            "language_detection": True,
            # Hindi is temporarily excluded from automatic detection.  The
            # router still keeps hi/hi-IN as a defensive Urdu voice alias for
            # provider metadata that may arrive despite this steering.
            "language_codes": ["en", "ur", "ar"],
            "mode": STT_MODE,
            "min_turn_silence": STT_MIN_TURN_SILENCE_MS,
            "max_turn_silence": STT_MAX_TURN_SILENCE_MS,
            "vad_threshold": STT_VAD_THRESHOLD,
        },
    )


def build_vad() -> inference.VAD:
    """Build the VAD threshold aligned with AssemblyAI's STT configuration."""

    return inference.VAD(
        model="silero",
        activation_threshold=STT_VAD_THRESHOLD,
    )


def build_turn_handling() -> TurnHandlingOptions:
    """Build the low-latency STT endpointing session options."""

    preemptive = configured_preemptive_generation()
    return TurnHandlingOptions(
        turn_detection=TURN_DETECTION_MODE,
        endpointing={
            "mode": ENDPOINTING_MODE,
            "min_delay": ENDPOINTING_MIN_DELAY_SECONDS,
        },
        preemptive_generation={
            "enabled": preemptive.enabled,
            "preemptive_tts": preemptive.preemptive_tts,
            "max_speech_duration": preemptive.max_speech_duration,
            "max_retries": preemptive.max_retries,
        },
    )


def build_llm(configuration: LLMConfiguration | None = None) -> inference.LLM:
    """Build the configured OpenAI LLM through LiveKit Inference."""

    configuration = configuration or configured_llm()

    return inference.LLM(
        model=configuration.model,
        extra_kwargs={
            "reasoning_effort": configuration.reasoning_effort,
            "max_completion_tokens": configuration.max_completion_tokens,
        },
    )


def configured_llm() -> LLMConfiguration:
    """Return validated LLM settings without making a provider request."""

    model = os.getenv(LLM_MODEL_ENV, DEFAULT_LLM_MODEL).strip()
    if model not in SUPPORTED_LLM_MODELS:
        supported = ", ".join(sorted(SUPPORTED_LLM_MODELS))
        raise RuntimeError(
            f"{LLM_MODEL_ENV} must be one of {supported}; received {model!r}"
        )

    reasoning_effort = (
        os.getenv(LLM_REASONING_EFFORT_ENV, DEFAULT_LLM_REASONING_EFFORT)
        .strip()
        .casefold()
    )
    if reasoning_effort not in SUPPORTED_LLM_REASONING_EFFORTS:
        supported = ", ".join(sorted(SUPPORTED_LLM_REASONING_EFFORTS))
        raise RuntimeError(
            f"{LLM_REASONING_EFFORT_ENV} must be one of {supported}; "
            f"received {reasoning_effort!r}"
        )

    raw_max_tokens = os.getenv(
        LLM_MAX_COMPLETION_TOKENS_ENV,
        str(DEFAULT_LLM_MAX_COMPLETION_TOKENS),
    ).strip()
    try:
        max_completion_tokens = int(raw_max_tokens)
    except ValueError as error:
        raise RuntimeError(
            f"{LLM_MAX_COMPLETION_TOKENS_ENV} must be an integer; "
            f"received {raw_max_tokens!r}"
        ) from error
    if (
        not LLM_MAX_COMPLETION_TOKENS_MIN
        <= max_completion_tokens
        <= (LLM_MAX_COMPLETION_TOKENS_MAX)
    ):
        raise RuntimeError(
            f"{LLM_MAX_COMPLETION_TOKENS_ENV} must be between "
            f"{LLM_MAX_COMPLETION_TOKENS_MIN} and "
            f"{LLM_MAX_COMPLETION_TOKENS_MAX}; received {max_completion_tokens}"
        )

    return LLMConfiguration(
        model=model,
        reasoning_effort=reasoning_effort,
        max_completion_tokens=max_completion_tokens,
    )


def configured_preemptive_generation() -> PreemptiveGenerationConfiguration:
    """Return bounded speculative-generation settings without provider I/O."""

    preemptive_tts = _configured_bool(
        PREEMPTIVE_TTS_ENV,
        DEFAULT_PREEMPTIVE_TTS,
    )

    raw_max_speech_duration = os.getenv(
        PREEMPTIVE_TTS_MAX_SPEECH_SECONDS_ENV,
        str(DEFAULT_PREEMPTIVE_TTS_MAX_SPEECH_SECONDS),
    ).strip()
    try:
        max_speech_duration = float(raw_max_speech_duration)
    except ValueError as error:
        raise RuntimeError(
            f"{PREEMPTIVE_TTS_MAX_SPEECH_SECONDS_ENV} must be a number; "
            f"received {raw_max_speech_duration!r}"
        ) from error
    if not 0.1 <= max_speech_duration <= 60.0:
        raise RuntimeError(
            f"{PREEMPTIVE_TTS_MAX_SPEECH_SECONDS_ENV} must be between 0.1 and "
            f"60.0 seconds; received {max_speech_duration}"
        )

    raw_max_retries = os.getenv(
        PREEMPTIVE_TTS_MAX_RETRIES_ENV,
        str(DEFAULT_PREEMPTIVE_TTS_MAX_RETRIES),
    ).strip()
    try:
        max_retries = int(raw_max_retries)
    except ValueError as error:
        raise RuntimeError(
            f"{PREEMPTIVE_TTS_MAX_RETRIES_ENV} must be an integer; "
            f"received {raw_max_retries!r}"
        ) from error
    if not 1 <= max_retries <= 10:
        raise RuntimeError(
            f"{PREEMPTIVE_TTS_MAX_RETRIES_ENV} must be between 1 and 10; "
            f"received {max_retries}"
        )

    return PreemptiveGenerationConfiguration(
        enabled=True,
        preemptive_tts=preemptive_tts,
        max_speech_duration=max_speech_duration,
        max_retries=max_retries,
    )


def _configured_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "true" if default else "false").strip().casefold()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean (true/false); received {raw_value!r}")


def configured_fast_property_results() -> bool:
    """Enable the candidate only in explicitly configured test sessions."""
    return _configured_bool(FAST_PROPERTY_RESULTS_ENV, False)


def configured_benchmark_labels() -> dict[str, str]:
    """Read optional run metadata used to keep benchmark records comparable."""

    return {
        label: value
        for env_name, label in _BENCHMARK_LABEL_ENV_VARS
        if (value := os.getenv(env_name, "").strip())
    }


def build_tts() -> inference.TTS:
    """Build the configured English Inworld TTS service."""

    return build_tts_for_language(ENGLISH_LANGUAGE)


def _configured_inworld_model() -> str:
    """Return the qualified LiveKit Inference Inworld model identifier."""

    model = os.getenv(INWORLD_TTS_MODEL_ENV, DEFAULT_INWORLD_TTS_MODEL).strip()
    if model != DEFAULT_INWORLD_TTS_MODEL:
        raise RuntimeError(
            f"{INWORLD_TTS_MODEL_ENV} must be set to "
            f"{DEFAULT_INWORLD_TTS_MODEL!r} for LiveKit Inference; direct "
            "Inworld plugin model identifiers are not supported"
        )
    return model


def _configured_voice(language: SupportedLanguage) -> tuple[str, str]:
    if language == ENGLISH_LANGUAGE:
        return (
            ENGLISH_TTS_VOICE_ENV,
            os.getenv(ENGLISH_TTS_VOICE_ENV, "").strip(),
        )
    if language == URDU_LANGUAGE:
        return URDU_TTS_VOICE_ENV, os.getenv(URDU_TTS_VOICE_ENV, "").strip()
    return ARABIC_TTS_VOICE_ENV, os.getenv(ARABIC_TTS_VOICE_ENV, "").strip()


def normalize_detected_language_code(language: object) -> str | None:
    """Normalize a provider tag to a recognized detected-language base code."""

    if not isinstance(language, str):
        return None
    base_language = language.strip().casefold().split("-", 1)[0]
    if base_language in DETECTED_LANGUAGE_BASES:
        return base_language
    return None


def _normalize_language_tag(language: object) -> str | None:
    if not isinstance(language, str) or not language.strip():
        return None
    parts = language.strip().replace("_", "-").split("-")
    normalized = [parts[0].casefold()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) in {2, 3} else part.title())
    return "-".join(normalized)


def normalize_language_code(language: object) -> SupportedLanguage | None:
    """Normalize a detected tag to the effective supported voice language."""

    detected_language = normalize_detected_language_code(language)
    if detected_language in {"ur", "hi"}:
        return "ur"
    if detected_language in {"en", "ar"}:
        return detected_language  # type: ignore[return-value]
    return None


def resolve_voice_route(language: object) -> VoiceRoute | None:
    """Resolve provider, voice, and locale without changing the transcript.

    Hindi is intentionally an effective-voice alias for Urdu for the current
    product requirement.  The original detected tag remains in the route so
    telemetry can distinguish ``hi`` from genuine ``ur`` detection.
    """

    detected_tag = _normalize_language_tag(language)
    if detected_tag is None:
        return None
    detected_language = detected_tag.split("-", 1)[0]
    if detected_language not in DETECTED_LANGUAGE_BASES:
        return None

    if detected_language == "en":
        return VoiceRoute(
            detected_language=detected_tag,
            effective_language="en",
            provider="inworld",
            model=_configured_inworld_model(),
            voice=os.getenv(ENGLISH_TTS_VOICE_ENV, "").strip(),
            locale=ENGLISH_TTS_LOCALE,
            alias_applied=False,
        )

    if detected_language in {"ur", "hi"}:
        return VoiceRoute(
            detected_language=detected_tag,
            effective_language="ur",
            provider="inworld",
            model=_configured_inworld_model(),
            voice=os.getenv(URDU_TTS_VOICE_ENV, "").strip(),
            locale=URDU_TTS_LOCALE,
            alias_applied=detected_language == "hi",
        )

    return VoiceRoute(
        detected_language=detected_tag,
        effective_language="ar",
        provider="inworld",
        model=_configured_inworld_model(),
        voice=os.getenv(ARABIC_TTS_VOICE_ENV, "").strip(),
        locale=ARABIC_TTS_LOCALE,
        alias_applied=False,
    )


def build_tts_for_language(language: SupportedLanguage) -> inference.TTS:
    """Build the configured TTS for one supported response language.

    All supported languages use LiveKit Inference with the shared Inworld
    TTS-2 Flash model. Voice IDs remain deployment configuration because they
    must be selected and evaluated in the Inworld catalog rather than guessed
    in application code.
    """

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported TTS language: {language!r}")

    route = resolve_voice_route(language)
    if route is None or route.effective_language != language:
        raise ValueError(f"unsupported TTS language: {language!r}")
    voice_variable, voice = _configured_voice(language)
    if not voice:
        raise RuntimeError(
            f"{voice_variable} must contain an Inworld voice ID before "
            f"{language} speech can be enabled"
        )

    return inference.TTS(
        model=route.model,
        voice=voice,
        language=route.locale,
    )
