import json
import logging

from livekit.agents import AgentServer, AgentSession, JobContext

from .config import (
    ENDPOINTING_MIN_DELAY_SECONDS,
    ENDPOINTING_MODE,
    STT_MAX_TURN_SILENCE_MS,
    STT_MIN_TURN_SILENCE_MS,
    STT_MODE,
    STT_MODEL,
    STT_VAD_THRESHOLD,
    TURN_DETECTION_MODE,
    build_llm,
    build_stt,
    build_tts,
    build_turn_handling,
    build_vad,
    configured_benchmark_labels,
    configured_fast_property_results,
    configured_llm,
    configured_preemptive_generation,
    validate_environment,
)
from .language_router import MultilingualTTSRouter
from .latency_metrics import LatencyRecorder, attach_session_listeners
from .receptionist import Receptionist
from .state import PropertySalesSessionData
from .welcome import LanguageSelectionAgent, WelcomeCoordinator

WELCOME_STATUS_TOPIC = "voiceforce_welcome"

validate_environment()
server = AgentServer()
logger = logging.getLogger(__name__)
_active_recorders: dict[str, LatencyRecorder] = {}


async def _on_session_end(ctx: JobContext) -> None:
    """Persist a privacy-conscious local SessionReport summary and flush metrics."""

    session_id = ctx.job.id
    recorder = _active_recorders.pop(session_id, None)
    if recorder is None:
        return

    try:
        report = ctx.make_session_report()
        recorder.record_session_summary(
            report.to_dict(include_chat_history=False, include_events=False)
        )
    except Exception:
        logger.exception("failed to create the LiveKit session latency report")
    finally:
        await recorder.close()


@server.rtc_session(
    agent_name="voiceforce-receptionist",
    on_session_end=_on_session_end,
)
async def voiceforce_receptionist(ctx: JobContext) -> None:
    """Start one receptionist session for a LiveKit room."""

    session_id = ctx.job.id
    ctx.log_context_fields = {"room": ctx.room.name, "job_id": session_id}
    llm_configuration = configured_llm()
    preemptive_configuration = configured_preemptive_generation()
    recorder = LatencyRecorder(
        session_id,
        session_labels={
            "room_name": ctx.room.name,
            "llm_model": llm_configuration.model,
            "llm_reasoning_effort": llm_configuration.reasoning_effort,
            "llm_max_completion_tokens": llm_configuration.max_completion_tokens,
            "turn_detection_mode": TURN_DETECTION_MODE,
            "stt_model": STT_MODEL,
            "stt_mode": STT_MODE,
            "endpointing_mode": ENDPOINTING_MODE,
            "endpointing_min_delay_seconds": ENDPOINTING_MIN_DELAY_SECONDS,
            "stt_min_turn_silence_ms": STT_MIN_TURN_SILENCE_MS,
            "stt_max_turn_silence_ms": STT_MAX_TURN_SILENCE_MS,
            "stt_vad_threshold": STT_VAD_THRESHOLD,
            "preemptive_generation_enabled": preemptive_configuration.enabled,
            "preemptive_tts_enabled": preemptive_configuration.preemptive_tts,
            "preemptive_tts_max_speech_seconds": (
                preemptive_configuration.max_speech_duration
            ),
            "preemptive_tts_max_retries": preemptive_configuration.max_retries,
            "fast_property_results_enabled": configured_fast_property_results(),
            **configured_benchmark_labels(),
        },
    )
    await recorder.start()
    _active_recorders[session_id] = recorder

    english_tts = build_tts()
    userdata = PropertySalesSessionData(
        active_agent="language_selector",
        selection_pending=True,
    )
    session = AgentSession[PropertySalesSessionData](
        stt=build_stt(),
        vad=build_vad(),
        llm=build_llm(llm_configuration),
        tts=english_tts,
        userdata=userdata,
        turn_handling=build_turn_handling(),
    )

    async def publish_welcome_status(payload: dict[str, object]) -> None:
        message = {
            "type": "voiceforce_welcome_status",
            "session_id": session_id,
            "room_name": ctx.room.name,
            **payload,
        }
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(message).encode("utf-8"),
                reliable=True,
                topic=WELCOME_STATUS_TOPIC,
            )
        except Exception:
            # Status is optional browser telemetry; the voice session must not
            # fail because a data packet could not be published.
            logger.warning("failed to publish welcome status", exc_info=True)

    selection_agent = LanguageSelectionAgent(
        latency_recorder=recorder,
        receptionist_factory=lambda chat_ctx: Receptionist(
            latency_recorder=recorder,
            chat_ctx=chat_ctx,
            session_data=userdata,
        ),
        status_publisher=publish_welcome_status,
    )
    language_router = MultilingualTTSRouter(
        selection_agent,
        session,
        english_tts=english_tts,
        recorder=recorder,
    )
    selection_agent.language_router = language_router
    attach_session_listeners(session, recorder)

    def track_caller_activity(event: object) -> None:
        if getattr(event, "new_state", None) == "speaking":
            userdata.caller_activity_revision += 1

    def track_caller_message(event: object) -> None:
        if getattr(getattr(event, "item", None), "role", None) == "user":
            userdata.caller_activity_revision += 1

    session.on("user_state_changed", track_caller_activity)
    session.on("conversation_item_added", track_caller_message)
    session.on("user_input_transcribed", language_router.on_user_input_transcribed)

    await session.start(
        agent=selection_agent,
        room=ctx.room,
    )

    await ctx.connect()

    await WelcomeCoordinator(
        session,
        language_router,
        recorder=recorder,
        status_publisher=publish_welcome_status,
    ).run()
