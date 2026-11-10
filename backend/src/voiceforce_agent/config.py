import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from livekit.agents import inference

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

ENGLISH_TTS_MODEL = "fishaudio/s2.1-pro"
ENGLISH_TTS_VOICE = "bf322df2096a46f18c579d0baa36f41d"
INWORLD_TTS_MODEL = "inworld/inworld-tts-2-flash"
# This is the LiveKit Inference model ID.  The direct Inworld plugin uses a
# different, unqualified identifier and must not be mixed into this path.
URDU_TTS_LOCALE = "ur-PK"
ARABIC_TTS_LOCALE = "ar-SA"


@dataclass(frozen=True)
class VoiceRoute:
    """The observable TTS decision for one detected language tag."""

    detected_language: str
    effective_language: SupportedLanguage
    provider: Literal["fishaudio", "inworld"]
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


def build_stt() -> inference.STT:
    """Build multilingual AssemblyAI Universal-3.6 Pro STT.

    Universal-3.6 Pro performs language detection and code-switching when no
    fixed language is supplied.  Keep the model's balanced preset as the
    default until language-specific accuracy and latency benchmarks justify a
    more aggressive setting.
    """

    return inference.STT(
        model="assemblyai/universal-3-6-pro",
        extra_kwargs={
            "language_detection": True,
            # Hindi is temporarily excluded from automatic detection.  The
            # router still keeps hi/hi-IN as a defensive Urdu voice alias for
            # provider metadata that may arrive despite this steering.
            "language_codes": ["en", "ur", "ar"],
            "mode": "balanced",
        },
    )


def build_llm() -> inference.LLM:
    """Build the OpenAI GPT-5 Mini LLM through LiveKit Inference."""

    return inference.LLM(
        model="openai/gpt-5-mini",
        provider="openai",
        extra_kwargs={"reasoning_effort": "low"},
    )


def build_tts() -> inference.TTS:
    """Build the Fish Audio S2.1 Pro English TTS service."""

    return inference.TTS(
        model=ENGLISH_TTS_MODEL,
        voice=ENGLISH_TTS_VOICE,
        language="en",
    )


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
            provider="fishaudio",
            model=ENGLISH_TTS_MODEL,
            voice=ENGLISH_TTS_VOICE,
            locale="en",
            alias_applied=False,
        )

    if detected_language in {"ur", "hi"}:
        return VoiceRoute(
            detected_language=detected_tag,
            effective_language="ur",
            provider="inworld",
            model=INWORLD_TTS_MODEL,
            voice=os.getenv("VOICEFORCE_INWORLD_URDU_VOICE", "").strip(),
            locale=URDU_TTS_LOCALE,
            alias_applied=detected_language == "hi",
        )

    return VoiceRoute(
        detected_language=detected_tag,
        effective_language="ar",
        provider="inworld",
        model=INWORLD_TTS_MODEL,
        voice=os.getenv("VOICEFORCE_INWORLD_ARABIC_VOICE", "").strip(),
        locale=ARABIC_TTS_LOCALE,
        alias_applied=False,
    )


def build_tts_for_language(language: SupportedLanguage) -> inference.TTS:
    """Build the configured TTS for one supported response language.

    English intentionally remains on the existing Fish Audio configuration.
    Inworld voice IDs are deployment configuration because the available
    native-language voices must be selected and evaluated in the Inworld
    catalog rather than guessed in application code.
    """

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported TTS language: {language!r}")

    route = resolve_voice_route(language)
    if route is None or route.effective_language != language:
        raise ValueError(f"unsupported TTS language: {language!r}")
    if language == ENGLISH_LANGUAGE:
        return build_tts()

    if not route.voice:
        voice_variable = (
            "VOICEFORCE_INWORLD_URDU_VOICE"
            if language == URDU_LANGUAGE
            else "VOICEFORCE_INWORLD_ARABIC_VOICE"
        )
        raise RuntimeError(
            f"{voice_variable} must contain an Inworld voice ID before "
            f"{language} speech can be enabled"
        )

    return inference.TTS(
        model=route.model,
        voice=route.voice,
        language=route.locale,
    )
