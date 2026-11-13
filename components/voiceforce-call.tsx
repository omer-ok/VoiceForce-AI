"use client";

import {
  SessionProvider,
  useAgent,
  useSession,
  useSessionContext,
} from "@livekit/components-react";
import { RoomEvent, TokenSource } from "livekit-client";
import { useEffect, useRef, useState } from "react";

import VoiceForceLatency from "@/components/voiceforce-latency";

const AGENT_NAME = "voiceforce-receptionist";
const AGENT_DEPLOYMENT =
  process.env.NODE_ENV === "development" ? "dev" : undefined;
const TOKEN_SOURCE = TokenSource.endpoint("/api/token");

export default function VoiceForceCall() {
  const session = useSession(TOKEN_SOURCE, {
    agentName: AGENT_NAME,
    deployment: AGENT_DEPLOYMENT,
    agentConnectTimeoutMilliseconds: 45_000,
  });

  return (
    <SessionProvider session={session}>
      <CallPanel />
    </SessionProvider>
  );
}

function CallPanel() {
  const session = useSessionContext();
  const agent = useAgent(session);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [welcomeStatus, setWelcomeStatus] = useState<WelcomeStatus>({
    phase: "idle",
  });
  const startAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const room = session.room;
    const transcriptionTopic = "lk.transcription";

    room.registerTextStreamHandler(
      transcriptionTopic,
      async (reader, participantInfo) => {
        const isAgentMessage =
          participantInfo.identity !== room.localParticipant.identity;
        const segmentId = reader.info.attributes?.["lk.segment_id"];
        let message = "";

        try {
          for await (const chunk of reader) {
            message += chunk;
            setMessages((currentMessages) => {
              const existingIndex = currentMessages.findIndex(
                (currentMessage) =>
                  currentMessage.id === reader.info.id ||
                  (segmentId !== undefined &&
                    currentMessage.segmentId === segmentId),
              );

              if (existingIndex === -1) {
                return [
                  ...currentMessages,
                  {
                    id: reader.info.id,
                    message,
                    segmentId,
                    type: isAgentMessage
                      ? "agentTranscript"
                      : "userTranscript",
                  },
                ];
              }

              const nextMessages = [...currentMessages];
              nextMessages[existingIndex] = {
                ...nextMessages[existingIndex],
                message,
                segmentId,
              };
              return nextMessages;
            });
          }
        } catch (caughtError) {
          // A call can end while the final transcript stream is still open.
          // Consume that expected interruption instead of surfacing an
          // unhandled DataStreamError from the browser.
          if (room.state !== "disconnected") {
            setError(
              caughtError instanceof Error
                ? caughtError.message
                : "The live transcript stream was interrupted.",
            );
          }
        }
      },
    );

    function onDataReceived(
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic?: string,
    ) {
      if (topic !== "voiceforce_welcome") return;

      try {
        const decoded = JSON.parse(new TextDecoder().decode(payload)) as {
          type?: string;
          phase?: WelcomeStatus["phase"];
          language?: string | null;
          label?: string;
          active_agent?: string;
          error_type?: string;
        };
        if (decoded.type !== "voiceforce_welcome_status" || !decoded.phase) {
          return;
        }
        setWelcomeStatus({
          phase: decoded.phase,
          language: decoded.language ?? null,
          label: decoded.label,
          activeAgent: decoded.active_agent,
          errorType: decoded.error_type,
        });
      } catch {
        // Ignore unrelated or malformed data packets from other participants.
      }
    }

    function onDisconnected() {
      setMessages([]);
    }

    room.on(RoomEvent.DataReceived, onDataReceived);
    room.on(RoomEvent.Disconnected, onDisconnected);

    return () => {
      room.off(RoomEvent.DataReceived, onDataReceived);
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.unregisterTextStreamHandler(transcriptionTopic);
    };
  }, [session.room]);

  async function startCall() {
    if (isStarting || session.isConnected) {
      return;
    }

    setError(null);
    setWelcomeStatus({ phase: "idle" });
    setIsStarting(true);
    const abortController = new AbortController();
    startAbortControllerRef.current = abortController;

    try {
      await session.start({
        signal: abortController.signal,
        tracks: {
          microphone: { enabled: true },
        },
      });
    } catch (caughtError) {
      if (!abortController.signal.aborted) {
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to start the call.",
        );
      }
      await session.end().catch(() => undefined);
    } finally {
      if (startAbortControllerRef.current === abortController) {
        startAbortControllerRef.current = null;
        setIsStarting(false);
      }
    }
  }

  async function endCall() {
    startAbortControllerRef.current?.abort();
    startAbortControllerRef.current = null;
    setIsStarting(false);
    setError(null);
    await session.end().catch(() => undefined);
    setWelcomeStatus({ phase: "idle" });
  }

  const status = getStatus(agent.state, isStarting, welcomeStatus);
  const isActive = isStarting || session.isConnected || agent.isPending;

  return (
    <section className="grid w-full gap-8 lg:grid-cols-[1.1fr_0.9fr]">
      <div className="rounded-3xl border border-white/10 bg-white/[0.07] p-8 shadow-2xl shadow-black/20 backdrop-blur sm:p-10">
        <p className="mb-4 text-sm font-medium uppercase tracking-[0.28em] text-cyan-300">
          Prime Properties Dubai
        </p>
        <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-white sm:text-6xl">
          Talk to your AI receptionist.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">
          Ask a question, share what you are looking for, or leave a message
          for the team. Start a private voice conversation whenever you are
          ready.
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-3">
          <button
            className="rounded-full bg-cyan-300 px-6 py-3 font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isActive}
            onClick={() => void startCall()}
            type="button"
          >
            {isStarting ? "Connecting…" : "Start Call"}
          </button>
          <button
            className="rounded-full border border-white/20 px-6 py-3 font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!isActive}
            onClick={() => void endCall()}
            type="button"
          >
            End Call
          </button>
        </div>

        <div className="mt-8 flex items-center gap-3 text-sm text-slate-300">
          <span
            aria-hidden="true"
            className={`h-2.5 w-2.5 rounded-full ${getStatusColor(agent.state)}`}
          />
          <span>{status}</span>
        </div>

        {welcomeStatus.phase !== "idle" ? (
          <div className="mt-4 rounded-2xl border border-cyan-300/15 bg-cyan-300/5 px-4 py-3 text-sm text-cyan-100">
            <p className="font-medium">{getWelcomeStatus(welcomeStatus)}</p>
            {welcomeStatus.phase === "listening" ? (
              <p className="mt-1 text-xs text-slate-400">
                Say English, Urdu with Aarav, or Arabic with Omar.
              </p>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="mt-4 rounded-2xl border border-red-300/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        ) : null}
      </div>

      <div className="flex min-h-[28rem] flex-col rounded-3xl border border-white/10 bg-slate-950/60 p-5 shadow-2xl shadow-black/20 backdrop-blur sm:p-6">
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <div>
            <p className="font-medium text-white">Conversation</p>
            <p className="mt-1 text-xs text-slate-400">
              Live transcripts appear here during the call.
            </p>
          </div>
          <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400">
            {agent.state}
          </span>
        </div>

        <div
          aria-live="polite"
          className="flex flex-1 flex-col gap-3 overflow-y-auto py-5"
          role="log"
        >
          {messages.length === 0 ? (
            <p className="m-auto max-w-xs text-center text-sm leading-6 text-slate-500">
              Start a call to begin speaking with the VoiceForce receptionist.
            </p>
          ) : (
            messages.map((message) => {
              const isAgentMessage = message.type === "agentTranscript";

              return (
                <div
                  className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    isAgentMessage
                      ? "self-start bg-white/10 text-slate-200"
                      : "self-end bg-cyan-300/15 text-cyan-50"
                  }`}
                  key={message.id}
                >
                  <p className="mb-1 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {isAgentMessage ? "Receptionist" : "You"}
                  </p>
                  <p>{message.message}</p>
                </div>
              );
            })
          )}
        </div>
      </div>

      <VoiceForceLatency />
    </section>
  );
}

function getStatus(
  state: ReturnType<typeof useAgent>["state"],
  isStarting: boolean,
  welcomeStatus: WelcomeStatus,
) {
  if (isStarting || state === "connecting") {
    return "Connecting to the receptionist…";
  }

  if (state === "speaking") {
    return "The receptionist is speaking";
  }

  if (state === "thinking") {
    return "The receptionist is thinking";
  }

  if (state === "listening") {
    return welcomeStatus.phase === "listening"
      ? "Listening for your language choice"
      : "Listening to you";
  }

  if (state === "failed") {
    return "The call could not connect";
  }

  if (state === "disconnected") {
    return "Ready to start a call";
  }

  return "Preparing the receptionist…";
}

type WelcomeStatus = {
  phase: "idle" | "introducing" | "listening" | "selected" | "failed";
  language?: string | null;
  label?: string;
  activeAgent?: string;
  errorType?: string;
};

type TranscriptMessage = {
  id: string;
  message: string;
  segmentId?: string;
  type: "agentTranscript" | "userTranscript";
};

function getWelcomeStatus(status: WelcomeStatus) {
  if (status.phase === "introducing") {
    return status.label ?? "Choosing your language";
  }

  if (status.phase === "listening") {
    return "Choose your language";
  }

  if (status.phase === "selected") {
    const language =
      status.language === "ur"
        ? "Urdu with Aarav"
        : status.language === "ar"
          ? "Arabic with Omar"
          : "English";
    return `${language} selected`;
  }

  if (status.phase === "failed") {
    return "The language selection prompt could not be completed";
  }

  return "Preparing language selection";
}

function getStatusColor(state: ReturnType<typeof useAgent>["state"]) {
  if (state === "speaking") {
    return "bg-cyan-300 shadow-[0_0_18px_rgba(103,232,249,0.9)]";
  }

  if (state === "listening") {
    return "bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.9)]";
  }

  if (state === "failed") {
    return "bg-red-300";
  }

  return "bg-amber-300";
}
