from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterable
from typing import Any

from livekit import rtc
from livekit.agents import Agent, ModelSettings, inference

from .config import (
    ENGLISH_LANGUAGE,
    SupportedLanguage,
    VoiceRoute,
    build_tts_for_language,
    normalize_language_code,
    resolve_voice_route,
)
from .latency_metrics import LatencyRecorder
from .state import PropertySalesSessionData

logger = logging.getLogger(__name__)


class MultilingualTTSRouter:
    """Select one cached TTS instance for the current detected language.

    Interim STT language events are observable but do not update session
    state. The final TTS selection is also performed at the synthesis boundary
    so a preemptive LLM generation cannot keep using the previous turn's TTS
    provider after a language switch.
    """

    def __init__(
        self,
        agent: Agent,
        session: Any,
        *,
        english_tts: inference.TTS,
        recorder: LatencyRecorder | None = None,
    ) -> None:
        self.agent = agent
        self.session = session
        self.recorder = recorder
        self._tts_by_language: dict[SupportedLanguage, inference.TTS] = {
            ENGLISH_LANGUAGE: english_tts,
        }
        self._active_language: SupportedLanguage = ENGLISH_LANGUAGE
        self._active_route = resolve_voice_route(ENGLISH_LANGUAGE)
        self._active_tts: inference.TTS = english_tts
        self._routing_error: tuple[VoiceRoute, str] | None = None
        self._configured_agent: Agent = agent

    @property
    def active_language(self) -> SupportedLanguage:
        return self._active_language

    @property
    def active_tts(self) -> inference.TTS:
        return self._active_tts

    def set_active_agent(self, agent: Agent) -> None:
        """Point routing at the active agent and copy the current TTS to it."""

        self.agent = agent
        # A handoff creates a new AgentActivity.  Copying the already selected
        # TTS to the new agent keeps the selected voice across that transition.
        agent.update_options(tts=self._active_tts)
        self._configured_agent = agent

    def activate_language(
        self,
        language: SupportedLanguage,
        *,
        turn_id: str | None = None,
        detected_language: str | None = None,
        reason: str = "explicit_language_selection",
    ) -> bool:
        """Apply a deliberate language route, such as welcome or selection."""

        route = resolve_voice_route(detected_language or language)
        if route is None or route.effective_language != language:
            route = resolve_voice_route(language)
        if route is None or route.effective_language != language:
            raise ValueError(f"unsupported effective TTS language: {language!r}")
        return self._select_route(route, turn_id=turn_id, reason=reason)

    def on_user_input_transcribed(self, event: Any) -> None:
        """Consume provider language metadata without logging transcript text."""

        detected_language = getattr(event, "language", None)
        route = resolve_voice_route(detected_language)
        is_final = bool(getattr(event, "is_final", False))
        confidence = getattr(event, "language_confidence", None)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = None

        detected_tag = (
            route.detected_language
            if route is not None
            else str(detected_language).strip().casefold()
            if isinstance(detected_language, str) and detected_language.strip()
            else None
        )
        effective_language = route.effective_language if route is not None else None

        self._record_detection(
            event,
            route=route,
            detected_tag=detected_tag,
            effective_language=effective_language,
            confidence=confidence,
            is_final=is_final,
        )
        logger.log(
            logging.INFO if is_final else logging.DEBUG,
            "speech language metadata received",
            extra={
                "detected_language": detected_tag,
                "effective_voice_language": effective_language,
                "metadata_stage": "final" if is_final else "interim",
                "language_confidence": confidence,
                "alias_applied": route.alias_applied if route is not None else False,
            },
        )

        # Interim language labels are useful for observability but must never
        # change the voice selected for a completed turn.
        if not is_final or route is None:
            return

        userdata = getattr(self.session, "userdata", None)
        if (
            isinstance(userdata, PropertySalesSessionData)
            and not userdata.selection_pending
        ):
            userdata.last_detected_language = detected_tag
            userdata.language_confidence = confidence

        # During the deterministic welcome and language-choice stage, the
        # language of a phrase such as "Urdu please" is not the selected
        # response language.  The selector agent handles that choice explicitly.
        if (
            isinstance(userdata, PropertySalesSessionData)
            and userdata.selection_pending
        ):
            return

        self._select_route(route, turn_id=getattr(event, "item_id", None))

    def _record_detection(
        self,
        event: Any,
        *,
        route: VoiceRoute | None,
        detected_tag: str | None,
        effective_language: SupportedLanguage | None,
        confidence: float | None,
        is_final: bool,
    ) -> None:
        if self.recorder is None:
            return

        labels = {
            "detected_language": detected_tag,
            "effective_voice_language": effective_language,
            "metadata_stage": "final" if is_final else "interim",
            "alias_applied": route.alias_applied if route is not None else False,
        }
        if route is not None:
            labels.update(
                {
                    "tts_service_provider": route.provider,
                    "tts_model": route.model,
                    "tts_voice": route.voice or None,
                    "tts_locale": route.locale,
                }
            )
        self.recorder.record_metric(
            stage="language",
            metric="language_detected",
            value=1,
            unit="event",
            source="session.user_input_transcribed",
            turn_id=getattr(event, "item_id", None),
            labels=labels,
        )
        if confidence is not None:
            self.recorder.record_metric(
                stage="language",
                metric="language_confidence",
                value=float(confidence),
                unit="ratio",
                source="session.user_input_transcribed",
                turn_id=getattr(event, "item_id", None),
                labels=labels,
            )

        if is_final:
            detection_latency = getattr(event, "language_detection_latency", None)
            if not isinstance(detection_latency, (int, float)) or isinstance(
                detection_latency, bool
            ):
                detection_latency = getattr(event, "language_detection_delay", None)
            if isinstance(detection_latency, (int, float)) and not isinstance(
                detection_latency, bool
            ):
                self.recorder.record_metric(
                    stage="language",
                    metric="language_detection_latency",
                    value=detection_latency,
                    unit="seconds",
                    source="session.user_input_transcribed",
                    turn_id=getattr(event, "item_id", None),
                    labels=labels,
                )
            else:
                self.recorder.record_missing(
                    stage="language",
                    metric="language_detection_latency",
                    unit="seconds",
                    source="session.user_input_transcribed",
                    turn_id=getattr(event, "item_id", None),
                    missing_reason=(
                        "installed STT event exposes the detected language but "
                        "not the provider detection timestamp"
                    ),
                    labels=labels,
                )

    def _select_route(
        self,
        route: VoiceRoute,
        *,
        turn_id: str | None,
        reason: str = "STT language metadata",
    ) -> bool:
        language = route.effective_language
        if language == self._active_language:
            try:
                # The active Agent may have changed since the last route
                # decision.  Re-apply the cached TTS to that agent even when
                # the effective language itself is unchanged.
                if self._configured_agent is not self.agent:
                    self.agent.update_options(tts=self._active_tts)
                    self._configured_agent = self.agent
            except Exception as error:
                self._routing_error = (route, type(error).__name__)
                return False
            self._routing_error = None
            self._set_effective_voice_language(language, turn_id=turn_id)
            self._record_route_decision(
                route,
                turn_id=turn_id,
                status="already_active",
                reason=reason,
            )
            userdata = getattr(self.session, "userdata", None)
            if isinstance(userdata, PropertySalesSessionData):
                userdata.preferred_language = language
            return True

        switch_started = time.perf_counter()
        switch_kind = "cached" if language in self._tts_by_language else "initialize"
        try:
            tts = self._tts_by_language.get(language)
            if tts is None:
                tts = build_tts_for_language(language)
                self._tts_by_language[language] = tts
            self._verify_tts_configuration(tts, route)
            self.agent.update_options(tts=tts)
            self._configured_agent = self.agent
        except Exception as error:
            switch_duration = max(0.0, time.perf_counter() - switch_started)
            error_type = type(error).__name__
            self._routing_error = (route, error_type)
            logger.error(
                "multilingual TTS route failed; no fallback voice will be used",
                extra={
                    "detected_language": route.detected_language,
                    "effective_voice_language": route.effective_language,
                    "tts_service_provider": route.provider,
                    "tts_model": route.model,
                    "tts_voice": route.voice or None,
                    "tts_locale": route.locale,
                    "error_type": error_type,
                },
            )
            if self.recorder is not None:
                self.recorder.record_metric(
                    stage="tts",
                    metric="tts_provider_switch_duration",
                    value=switch_duration,
                    unit="seconds",
                    source="language_router",
                    labels={
                        "detected_language": route.detected_language,
                        "effective_voice_language": route.effective_language,
                        "tts_service_provider": route.provider,
                        "tts_model": route.model,
                        "tts_voice": route.voice or None,
                        "tts_locale": route.locale,
                        "switch_kind": switch_kind,
                        "status": "failed",
                        "error_type": error_type,
                    },
                )
                self.recorder.record_metric(
                    stage="tts",
                    metric="tts_provider_switch_failed",
                    value=1,
                    unit="event",
                    source="language_router",
                    labels={
                        "detected_language": route.detected_language,
                        "effective_voice_language": route.effective_language,
                        "tts_service_provider": route.provider,
                        "tts_model": route.model,
                        "tts_voice": route.voice or None,
                        "tts_locale": route.locale,
                        "switch_kind": switch_kind,
                        "error_type": error_type,
                    },
                )
                self.recorder.record_missing(
                    stage="tts",
                    metric="language_route",
                    unit="event",
                    source="language_router",
                    missing_reason="language TTS configuration or provider unavailable",
                    labels={
                        "detected_language": route.detected_language,
                        "effective_voice_language": route.effective_language,
                        "tts_service_provider": route.provider,
                        "tts_model": route.model,
                        "tts_voice": route.voice or None,
                        "tts_locale": route.locale,
                    },
                )
            return False

        switch_duration = max(0.0, time.perf_counter() - switch_started)
        previous_language = self._active_language
        self._active_language = language
        self._active_route = route
        self._active_tts = tts
        self._routing_error = None
        self._set_effective_voice_language(language, turn_id=turn_id)
        userdata = getattr(self.session, "userdata", None)
        if isinstance(userdata, PropertySalesSessionData):
            userdata.preferred_language = language
        if self.recorder is not None:
            self.recorder.record_metric(
                stage="tts",
                metric="tts_provider_switch_duration",
                value=switch_duration,
                unit="seconds",
                source="language_router",
                labels={
                    "language_code": language,
                    "switch_kind": switch_kind,
                    "status": "ok",
                    "tts_provider": getattr(tts, "provider", None),
                    "tts_service_provider": route.provider,
                    "tts_model": route.model,
                    "tts_voice": route.voice or None,
                    "tts_locale": route.locale,
                    "detected_language": route.detected_language,
                    "effective_voice_language": route.effective_language,
                    "alias_applied": route.alias_applied,
                },
            )
            self.recorder.record_metric(
                stage="language",
                metric="language_switched",
                value=1,
                unit="event",
                source="language_router",
                labels={
                    "from_language": previous_language,
                    "to_language": language,
                    "tts_provider": tts.provider,
                    "tts_service_provider": route.provider,
                    "tts_model": route.model,
                    "tts_voice": route.voice or None,
                    "tts_locale": route.locale,
                    "detected_language": route.detected_language,
                    "effective_voice_language": route.effective_language,
                    "alias_applied": route.alias_applied,
                },
            )
        self._record_route_decision(
            route,
            turn_id=turn_id,
            status="configured",
            reason=reason,
        )
        return True

    @staticmethod
    def _verify_tts_configuration(tts: inference.TTS, route: VoiceRoute) -> None:
        options = getattr(tts, "_opts", None)
        actual_voice = getattr(options, "voice", None)
        actual_locale = getattr(options, "language", None)
        if (
            getattr(tts, "model", None) != route.model
            or actual_voice != route.voice
            or str(actual_locale) != route.locale
        ):
            raise RuntimeError(
                "active TTS configuration does not match the requested voice route"
            )

    def _record_route_decision(
        self,
        route: VoiceRoute,
        *,
        turn_id: str | None,
        status: str,
        reason: str,
    ) -> None:
        if self.recorder is None:
            return
        self.recorder.record_metric(
            stage="language",
            metric="language_route_decision",
            value=1,
            unit="event",
            source="language_router",
            turn_id=turn_id,
            labels={
                "detected_language": route.detected_language,
                "effective_voice_language": route.effective_language,
                "tts_service_provider": route.provider,
                "tts_model": route.model,
                "tts_voice": route.voice or None,
                "tts_locale": route.locale,
                "alias_applied": route.alias_applied,
                "status": status,
                "reason": reason,
            },
        )

    def _set_effective_voice_language(
        self, language: SupportedLanguage, *, turn_id: str | None
    ) -> None:
        if self.recorder is None:
            return
        setter = getattr(self.recorder, "set_effective_voice_language", None)
        if callable(setter):
            setter(language, turn_id=turn_id)

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
        *,
        agent: Agent | None = None,
    ) -> AsyncIterable[rtc.AudioFrame]:
        language = normalize_language_code(
            getattr(getattr(self.session, "userdata", None), "preferred_language", None)
        )
        if self._routing_error is not None:
            route, error_type = self._routing_error
            raise RuntimeError(
                f"TTS route unavailable for {route.locale} ({error_type}); "
                "refusing to fall back to another voice"
            )
        if language is not None and language != self._active_language:
            route = resolve_voice_route(language)
            if route is None:
                raise RuntimeError(f"unsupported effective TTS language: {language}")
            self._select_route(route, turn_id=None)
        active_route = self._active_route
        try:
            first_frame = True
            async for frame in Agent.default.tts_node(
                agent or self.agent, text, model_settings
            ):
                if first_frame:
                    first_frame = False
                    logger.info(
                        "TTS route produced audio",
                        extra={
                            "detected_language": (
                                active_route.detected_language
                                if active_route is not None
                                else None
                            ),
                            "effective_voice_language": (
                                active_route.effective_language
                                if active_route is not None
                                else self._active_language
                            ),
                            "tts_service_provider": (
                                active_route.provider
                                if active_route is not None
                                else None
                            ),
                            "tts_model": (
                                active_route.model if active_route is not None else None
                            ),
                            "tts_voice": (
                                active_route.voice if active_route is not None else None
                            ),
                            "tts_locale": (
                                active_route.locale
                                if active_route is not None
                                else None
                            ),
                        },
                    )
                    if self.recorder is not None and active_route is not None:
                        self.recorder.record_metric(
                            stage="tts",
                            metric="tts_route_audio_started",
                            value=1,
                            unit="event",
                            source="language_router.tts_node",
                            labels={
                                "detected_language": active_route.detected_language,
                                "effective_voice_language": active_route.effective_language,
                                "tts_service_provider": active_route.provider,
                                "tts_model": active_route.model,
                                "tts_voice": active_route.voice or None,
                                "tts_locale": active_route.locale,
                                "alias_applied": active_route.alias_applied,
                            },
                        )
                yield frame
        except Exception as error:
            logger.error(
                "multilingual TTS synthesis failed",
                extra={
                    "language_code": language or self._active_language,
                    "error_type": type(error).__name__,
                    "tts_service_provider": (
                        active_route.provider if active_route is not None else None
                    ),
                    "tts_model": active_route.model
                    if active_route is not None
                    else None,
                    "tts_voice": active_route.voice
                    if active_route is not None
                    else None,
                    "tts_locale": active_route.locale
                    if active_route is not None
                    else None,
                },
            )
            if self.recorder is not None:
                self.recorder.record_metric(
                    stage="tts",
                    metric="tts_synthesis_failed",
                    value=1,
                    unit="event",
                    source="language_router.tts_node",
                    labels={
                        "language_code": language or self._active_language,
                        "error_type": type(error).__name__,
                        "detected_language": (
                            active_route.detected_language
                            if active_route is not None
                            else None
                        ),
                        "effective_voice_language": (
                            active_route.effective_language
                            if active_route is not None
                            else self._active_language
                        ),
                        "tts_service_provider": (
                            active_route.provider if active_route is not None else None
                        ),
                        "tts_model": active_route.model
                        if active_route is not None
                        else None,
                        "tts_voice": active_route.voice
                        if active_route is not None
                        else None,
                        "tts_locale": active_route.locale
                        if active_route is not None
                        else None,
                    },
                )
                self.recorder.record_metric(
                    stage="tts",
                    metric="tts_provider_error",
                    value=1,
                    unit="event",
                    source="language_router.tts_node",
                    labels={
                        "language_code": language or self._active_language,
                        "error_type": type(error).__name__,
                        "detected_language": (
                            active_route.detected_language
                            if active_route is not None
                            else None
                        ),
                        "effective_voice_language": (
                            active_route.effective_language
                            if active_route is not None
                            else self._active_language
                        ),
                        "tts_service_provider": (
                            active_route.provider if active_route is not None else None
                        ),
                        "tts_model": active_route.model
                        if active_route is not None
                        else None,
                        "tts_voice": active_route.voice
                        if active_route is not None
                        else None,
                        "tts_locale": active_route.locale
                        if active_route is not None
                        else None,
                    },
                )
            raise
