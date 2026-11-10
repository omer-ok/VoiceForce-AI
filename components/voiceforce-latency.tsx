"use client";

import {
  AudioTrack,
  useAgent,
  useSessionContext,
  useTracks,
} from "@livekit/components-react";
import {
  RoomEvent,
  Track,
  type RemoteParticipant,
  type RemoteTrack,
  type RemoteTrackPublication,
} from "livekit-client";
import { useEffect, useMemo, useRef, useState } from "react";

import { BrowserLatencyRecorder } from "@/lib/latency";

export default function VoiceForceLatency() {
  const session = useSessionContext();
  const agent = useAgent(session);
  const remoteAudioTracks = useTracks(
    [Track.Source.Microphone, Track.Source.ScreenShareAudio, Track.Source.Unknown],
    {
      updateOnlyOn: [],
      onlySubscribed: true,
      room: session.room,
    },
  ).filter(
    (trackRef) =>
      !trackRef.participant.isLocal &&
      trackRef.publication.kind === Track.Kind.Audio,
  );
  const recorderRef = useRef<BrowserLatencyRecorder | null>(null);
  const [browserSessionId] = useState(createBrowserSessionId);
  const recorder = useMemo(
    () =>
      new BrowserLatencyRecorder(browserSessionId, () => ({
        room_name: session.room.name || null,
        local_participant_identity:
          session.room.localParticipant.identity || null,
      })),
    [browserSessionId, session.room],
  );

  useEffect(() => {
    recorderRef.current = recorder;
    return () => {
      recorderRef.current = null;
    };
  }, [recorder]);

  useEffect(() => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    recorder.record({
      stage: "session",
      metric: "connection_state",
      value: 1,
      unit: "event",
      labels: { state: session.connectionState },
    });
    if (session.connectionState === "connecting") {
      recorder.record({
        stage: "session",
        metric: "start_requested",
        value: 1,
        unit: "event",
      });
    }
  }, [session.connectionState]);

  useEffect(() => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    recorder.record({
      stage: "agent_state",
      metric: "state_changed",
      value: 1,
      unit: "event",
      labels: { state: agent.state },
    });
  }, [agent.state]);

  useEffect(() => {
    const recorder = recorderRef.current;
    const microphone = session.local.microphoneTrack;
    if (!recorder || !microphone) return;

    recorder.record({
      stage: "microphone",
      metric: "ready",
      value: 1,
      unit: "event",
      labels: { source: microphone.source },
    });
    recorder.record({
      stage: "microphone",
      metric: "published",
      value: 1,
      unit: "event",
      labels: { source: microphone.source },
    });
  }, [session.local.microphoneTrack]);

  useEffect(() => {
    const recorder = recorderRef.current;
    const room = session.room;
    if (!recorder) return;

    const onConnected = () => {
      recorder.record({
        stage: "session",
        metric: "connected",
        value: 1,
        unit: "event",
      });
    };
    const onDisconnected = () => {
      recorder.record({
        stage: "session",
        metric: "disconnected",
        value: 1,
        unit: "event",
      });
    };
    const onTrackPublished = (
      publication: RemoteTrackPublication,
      participant: RemoteParticipant,
    ) => {
      if (publication.kind !== Track.Kind.Audio) return;
      recorder.record({
        stage: "remote_track",
        metric: "published",
        value: 1,
        unit: "event",
        labels: {
          participant_identity: participant.identity ?? null,
          track_id: publication.trackSid ?? null,
        },
      });
    };
    const onTrackSubscribed = (
      track: RemoteTrack,
      publication: RemoteTrackPublication,
      participant: RemoteParticipant,
    ) => {
      if (publication.kind !== Track.Kind.Audio || track.kind !== Track.Kind.Audio) {
        return;
      }

      recorder.record({
        stage: "remote_track",
        metric: "subscribed",
        value: 1,
        unit: "event",
        labels: {
          participant_identity: participant.identity ?? null,
          track_id: publication.trackSid ?? track.sid ?? null,
        },
      });

      void track
        .getRTCStatsReport()
        .then((report) => {
          if (!report) return;
          report.forEach((stat) => {
            const inbound = stat as RTCStats & {
              kind?: string;
              jitter?: number;
              packetsLost?: number;
            };
            if (inbound.type !== "inbound-rtp" || inbound.kind !== "audio") {
              return;
            }
            if (typeof inbound.jitter === "number") {
              recorder.record({
                stage: "webrtc",
                metric: "remote_audio_jitter",
                value: inbound.jitter,
                unit: "seconds",
                labels: {
                  participant_identity: participant.identity,
                  track_id: publication.trackSid ?? track.sid ?? null,
                },
              });
            }
            if (typeof inbound.packetsLost === "number") {
              recorder.record({
                stage: "webrtc",
                metric: "remote_audio_packets_lost",
                value: inbound.packetsLost,
                unit: "count",
                labels: {
                  participant_identity: participant.identity,
                  track_id: publication.trackSid ?? track.sid ?? null,
                },
              });
            }
          });
        })
        .catch(() => undefined);
    };
    const onTrackUnsubscribed = (
      track: RemoteTrack,
      publication: RemoteTrackPublication,
      participant: RemoteParticipant,
    ) => {
      if (track.kind !== Track.Kind.Audio) return;
      recorder.record({
        stage: "remote_track",
        metric: "unsubscribed",
        value: 1,
        unit: "event",
        labels: {
          participant_identity: participant.identity ?? null,
          track_id: publication.trackSid ?? track.sid ?? null,
        },
      });
    };
    const onSubscriptionFailed = (
      trackSid: string,
      participant: RemoteParticipant,
    ) => {
      recorder.record({
        stage: "remote_track",
        metric: "subscription_failed",
        value: 1,
        unit: "event",
        labels: {
          participant_identity: participant.identity ?? null,
          track_id: trackSid,
        },
      });
    };
    const onPlaybackStatusChanged = (playing: boolean) => {
      recorder.record({
        stage: "media_playback",
        metric: playing ? "started_or_recovered" : "interrupted",
        value: 1,
        unit: "event",
        labels: {
          can_play_audio: playing,
          source: "livekit_room_audio_playback_status",
        },
      });
    };

    room.on(RoomEvent.Connected, onConnected);
    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.TrackPublished, onTrackPublished);
    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
    room.on(RoomEvent.TrackSubscriptionFailed, onSubscriptionFailed);
    room.on(RoomEvent.AudioPlaybackStatusChanged, onPlaybackStatusChanged);

    return () => {
      room.off(RoomEvent.Connected, onConnected);
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.TrackPublished, onTrackPublished);
      room.off(RoomEvent.TrackSubscribed, onTrackSubscribed);
      room.off(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
      room.off(RoomEvent.TrackSubscriptionFailed, onSubscriptionFailed);
      room.off(RoomEvent.AudioPlaybackStatusChanged, onPlaybackStatusChanged);
    };
  }, [session.room]);

  return (
    <div style={{ display: "none" }}>
      {remoteAudioTracks.map((trackRef) => (
        <MeasuredAudioTrack
          key={`${trackRef.participant.identity}-${trackRef.publication.trackSid}`}
          recorder={recorder}
          trackRef={trackRef}
        />
      ))}
    </div>
  );
}

function createBrowserSessionId() {
  const generatedId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `browser-${generatedId}`;
}

function MeasuredAudioTrack({
  recorder,
  trackRef,
}: {
  recorder: BrowserLatencyRecorder | null;
  trackRef: Parameters<typeof AudioTrack>[0]["trackRef"];
}) {
  const participantIdentity = trackRef?.participant.identity ?? null;
  const trackId = trackRef?.publication.trackSid ?? null;
  const labels = {
    participant_identity: participantIdentity,
    track_id: trackId,
    media_element: "html_audio",
  };

  return (
    <AudioTrack
      onCanPlay={() => {
        recorder?.record({
          stage: "media_element",
          metric: "can_play",
          value: 1,
          unit: "event",
          labels,
        });
      }}
      onError={(event) => {
        const mediaError = event.currentTarget.error;
        recorder?.record({
          stage: "media_element",
          metric: "error",
          unit: "event",
          available: false,
          missing_reason: mediaError?.message || "HTMLAudioElement error",
          labels: {
            ...labels,
            error_code: mediaError?.code ?? null,
          },
        });
      }}
      onPlaying={() => {
        recorder?.record({
          stage: "media_element",
          metric: "playing",
          value: 1,
          unit: "event",
          labels,
        });
      }}
      trackRef={trackRef}
    />
  );
}
