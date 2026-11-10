import json
import logging

from livekit.agents import (
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    inference,
)

from .config import build_llm, build_stt, build_tts, validate_environment
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
    recorder = LatencyRecorder(
        session_id,
        session_labels={"room_name": ctx.room.name},
    )
    await recorder.start()
    _active_recorders[session_id] = recorder

    turn_detector = inference.TurnDetector()
    english_tts = build_tts()
    userdata = PropertySalesSessionData(
        active_agent="language_selector",
        selection_pending=True,
    )
    session = AgentSession[PropertySalesSessionData](
        stt=build_stt(),
        llm=build_llm(),
        tts=english_tts,
        userdata=userdata,
        turn_handling=TurnHandlingOptions(
            turn_detection=turn_detector,
            preemptive_generation={"enabled": True},
        ),
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
    attach_session_listeners(session, recorder, turn_detector=turn_detector)
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
