import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import inference

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPOSITORY_ROOT / ".env.local")


def validate_environment() -> None:
    """Fail clearly when the shared root environment is missing LiveKit settings."""

    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required LiveKit environment variables: {names}")


def build_stt() -> inference.STT:
    """Build the English AssemblyAI Universal-3.6 Pro STT service."""

    return inference.STT(
        model="assemblyai/universal-3-6-pro",
        language="en",
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
        model="fishaudio/s2.1-pro",
        voice="bf322df2096a46f18c579d0baa36f41d",
        language="en",
    )
