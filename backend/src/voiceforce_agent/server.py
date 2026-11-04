from livekit.agents import (
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    inference,
)

from .config import build_llm, build_stt, build_tts, validate_environment
from .receptionist import Receptionist

validate_environment()
server = AgentServer()


@server.rtc_session(agent_name="voiceforce-receptionist")
async def voiceforce_receptionist(ctx: JobContext) -> None:
    """Start one receptionist session for a LiveKit room."""

    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        stt=build_stt(),
        llm=build_llm(),
        tts=build_tts(),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            preemptive_generation={"enabled": True},
        ),
    )

    await session.start(
        agent=Receptionist(),
        room=ctx.room,
    )

    await ctx.connect()

    await session.generate_reply(
        instructions=(
            "Greet the caller as the Prime Properties Dubai receptionist "
            "and ask how you can help today."
        )
    )
