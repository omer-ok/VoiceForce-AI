# ruff: noqa: RUF001

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import Agent, ChatContext, ModelSettings, RunContext, function_tool

from .config import SupportedLanguage
from .language_router import MultilingualTTSRouter
from .latency_metrics import LatencyRecorder
from .receptionist import Receptionist
from .state import PropertySalesSessionData

logger = logging.getLogger(__name__)

WELCOME_INTRODUCTIONS: tuple[tuple[SupportedLanguage, str, str], ...] = (
    (
        "en",
        "English",
        "Hello! Welcome to VoiceForce AI. I'm your English-speaking assistant. "
        "Let me introduce our other language assistants.",
    ),
    (
        "ur",
        "Urdu / Aarav",
        "السلام علیکم! میں آرو ہوں، آپ کا اردو اسسٹنٹ۔ میں آپ کی اردو میں مدد کر سکتا ہوں۔",
    ),
    (
        "ar",
        "Arabic / Omar",
        "مرحباً! أنا عمر، مساعدك باللغة العربية. يسعدني مساعدتك باللغة العربية.",
    ),
)

LANGUAGE_SELECTION_PROMPTS: tuple[tuple[SupportedLanguage, str], ...] = (
    ("en", "Please choose English, Urdu with Aarav, or Arabic with Omar."),
    ("ur", "براہِ کرم انگریزی، آرو کے ساتھ اردو، یا عمر کے ساتھ عربی منتخب کریں۔"),
    ("ar", "يرجى اختيار الإنجليزية، أو الأردية مع آرو، أو العربية مع عمر."),
)

_LANGUAGE_ALIASES: dict[str, SupportedLanguage] = {
    "en": "en",
    "en-us": "en",
    "english": "en",
    "english please": "en",
    "ur": "ur",
    "ur-pk": "ur",
    "urdu": "ur",
    "urdu please": "ur",
    "urdu mein": "ur",
    "urdu mein baat karein": "ur",
    "اردو": "ur",
    "hi": "ur",
    "hi-in": "ur",
    "hindi": "ur",
    "ar": "ar",
    "ar-sa": "ar",
    "arabic": "ar",
    "arabic please": "ar",
    "العربية": "ar",
    "العربي": "ar",
}

StatusPublisher = Callable[[dict[str, Any]], Awaitable[None]]
ReceptionistFactory = Callable[[ChatContext], Receptionist]


def normalize_language_selection(value: object) -> SupportedLanguage | None:
    """Validate the selector tool's normalized language argument.

    The LLM is responsible for understanding the caller's natural wording. This
    helper only validates the short value returned by the tool call and keeps
    the existing Hindi-to-Urdu compatibility alias explicit.
    """

    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().casefold().replace("_", "-").split())
    return _LANGUAGE_ALIASES.get(normalized)


class LanguageSelectionAgent(Agent):
    """Small, tool-only agent used before the property receptionist."""

    def __init__(
        self,
        *,
        latency_recorder: LatencyRecorder | None = None,
        receptionist_factory: ReceptionistFactory,
        status_publisher: StatusPublisher | None = None,
    ) -> None:
        self.language_router: MultilingualTTSRouter | None = None
        self.latency_recorder = latency_recorder
        self._receptionist_factory = receptionist_factory
        self._status_publisher = status_publisher
        super().__init__(
            id="language_selector",
            instructions=(
                "You are the VoiceForce AI language selector. The caller has just "
                "heard short introductions in English, Pakistani Urdu, and Arabic. "
                "Do not answer property questions and do not use any property tools. "
                "Listen for one clear language choice. If the caller says English, "
                "English please, Urdu, Urdu mein, اردو, or Arabic, العربية, call "
                "select_language with exactly en, ur, or ar. A caller may say the "
                "choice in another language, such as 'Urdu please' in English. Do "
                "not choose based only on the language used to say the choice. If "
                "the choice is ambiguous or contains multiple languages, ask them "
                "to choose English, Urdu with Aarav, or Arabic with Omar. Keep that "
                "clarification very short. Treat hi or hi-IN as the existing Urdu "
                "compatibility alias, not as a Hindi response language."
            ),
        )

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncIterator[rtc.AudioFrame]:
        router = self.language_router
        if router is not None:
            async for frame in router.tts_node(text, model_settings, agent=self):
                yield frame
            return

        async for frame in Agent.default.tts_node(self, text, model_settings):
            yield frame

    @function_tool()
    async def select_language(self, context: RunContext[Any], language: str):
        """Select English, Urdu with Aarav, or Arabic with Omar."""

        userdata = context.userdata
        if not isinstance(userdata, PropertySalesSessionData):
            raise RuntimeError("language selection state is unavailable")

        userdata.selection_attempts += 1
        selected_language = normalize_language_selection(language)
        if selected_language is None:
            return (
                "Please choose only one of these languages: English, Urdu with "
                "Aarav, or Arabic with Omar."
            )

        router = self.language_router
        if router is None:
            raise RuntimeError("language TTS router is unavailable")

        route_applied = router.activate_language(
            selected_language,
            detected_language=selected_language,
            reason="language_selection",
        )
        if not route_applied:
            raise RuntimeError(
                f"the selected {selected_language} voice could not be activated"
            )

        try:
            receptionist = self._receptionist_factory(
                self.chat_ctx.copy(exclude_instructions=True)
            )
            receptionist.language_router = router
            router.set_active_agent(receptionist)
        except Exception:
            # Keep the selector and current route in place if the handoff cannot
            # be prepared. No English fallback is introduced here.
            router.set_active_agent(self)
            raise

        userdata.selected_language = selected_language
        userdata.preferred_language = selected_language
        userdata.selection_pending = False
        userdata.active_agent = "receptionist"
        if self._status_publisher is not None:
            await self._status_publisher(
                {
                    "phase": "selected",
                    "language": selected_language,
                    "active_agent": "receptionist",
                }
            )

        confirmations = {
            "en": "English selected. How can I help you with Prime Properties Dubai?",
            "ur": "اردو منتخب کی گئی ہے۔ میں پرائم پراپرٹیز دبئی میں آپ کی مدد کر سکتا ہوں۔",
            "ar": "تم اختيار العربية. كيف يمكنني مساعدتك في برايم بروبرتيز دبي؟",
        }
        # Returning the new agent and a short result uses LiveKit's documented
        # tool handoff path: the confirmation is generated before the handoff,
        # then the same session continues with the receptionist's tools.
        return receptionist, confirmations[selected_language]


class WelcomeCoordinator:
    """Play the deterministic multilingual welcome once per AgentSession."""

    def __init__(
        self,
        session: Any,
        router: MultilingualTTSRouter,
        *,
        recorder: LatencyRecorder | None = None,
        status_publisher: StatusPublisher | None = None,
    ) -> None:
        self.session = session
        self.router = router
        self.recorder = recorder
        self.status_publisher = status_publisher

    async def run(self) -> bool:
        userdata = getattr(self.session, "userdata", None)
        if not isinstance(userdata, PropertySalesSessionData):
            raise RuntimeError("welcome sequence state is unavailable")
        if userdata.welcome_sequence_started or userdata.welcome_sequence_completed:
            return False

        userdata.welcome_sequence_started = True
        userdata.selection_pending = True
        userdata.active_agent = "language_selector"
        sequence_started = time.perf_counter()
        self._record("welcome_sequence_started")

        try:
            for language, label, text in WELCOME_INTRODUCTIONS:
                await self._speak_step(
                    language,
                    label=label,
                    text=text,
                    step="introduction",
                )

            for language, text in LANGUAGE_SELECTION_PROMPTS:
                await self._speak_step(
                    language,
                    label=f"{language} selection prompt",
                    text=text,
                    step="selection_prompt",
                )

            userdata.welcome_sequence_completed = True
            self._record(
                "welcome_sequence_duration",
                max(0.0, time.perf_counter() - sequence_started),
                unit="seconds",
            )
            self._record("welcome_sequence_completed")
            await self._publish(
                {
                    "phase": "listening",
                    "language": None,
                    "active_agent": "language_selector",
                }
            )
            return True
        except Exception as error:
            self._record(
                "welcome_sequence_failed",
                labels={"error_type": type(error).__name__},
            )
            await self._publish(
                {
                    "phase": "failed",
                    "language": None,
                    "active_agent": "language_selector",
                    "error_type": type(error).__name__,
                }
            )
            raise

    async def _speak_step(
        self,
        language: SupportedLanguage,
        *,
        label: str,
        text: str,
        step: str,
    ) -> None:
        await self._publish(
            {
                "phase": "introducing",
                "language": language,
                "label": label,
                "active_agent": "language_selector",
            }
        )
        if not self.router.activate_language(language, reason=f"welcome_{step}"):
            raise RuntimeError(f"unable to activate the {language} welcome voice")

        started = time.perf_counter()
        handle = self.session.say(
            text,
            allow_interruptions=False,
            add_to_chat_ctx=False,
        )
        await handle.wait_for_playout()
        error = handle.exception()
        if error is not None:
            raise error
        self._record(
            "welcome_step_duration",
            max(0.0, time.perf_counter() - started),
            unit="seconds",
            labels={"language": language, "step": step},
        )

    async def _publish(self, payload: dict[str, Any]) -> None:
        if self.status_publisher is None:
            return
        try:
            await self.status_publisher(payload)
        except Exception:
            # Status is useful UI telemetry, but must never prevent the audio
            # sequence or language handoff from continuing.
            logger.warning("failed to publish welcome status", exc_info=True)

    def _record(
        self,
        metric: str,
        value: float = 1,
        *,
        unit: str = "event",
        labels: dict[str, Any] | None = None,
    ) -> None:
        if self.recorder is None:
            return
        self.recorder.record_metric(
            stage="welcome",
            metric=metric,
            value=value,
            unit=unit,
            source="welcome_coordinator",
            labels=labels,
        )
