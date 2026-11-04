from voiceforce_agent.config import build_llm, build_stt, build_tts
from voiceforce_agent.receptionist import Receptionist


def test_inference_models_are_configured() -> None:
    stt = build_stt()
    llm = build_llm()
    tts = build_tts()

    assert (stt.model, stt.provider) == ("assemblyai/universal-3-6-pro", "livekit")
    assert (llm.model, llm.provider) == ("openai/gpt-5-mini", "livekit")
    assert (tts.model, tts.provider) == ("fishaudio/s2.1-pro", "livekit")


def test_receptionist_is_grounded_for_initial_milestone() -> None:
    instructions = Receptionist().instructions

    assert "Do not invent property availability" in instructions
    assert "Historical sales tools are available" in instructions
    assert "cannot verify live availability" in instructions
