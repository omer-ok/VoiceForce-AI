import {
  AccessToken,
  RoomAgentDispatch,
  RoomConfiguration,
} from "livekit-server-sdk";
import { NextRequest, NextResponse } from "next/server";

const AGENT_NAME = "voiceforce-receptionist";
const TOKEN_TTL = "10m";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function expectedDeployment(): string | undefined {
  const configuredDeployment = process.env.LIVEKIT_AGENT_DEPLOYMENT?.trim();

  if (configuredDeployment) {
    return configuredDeployment;
  }

  return process.env.NODE_ENV === "development" ? "dev" : undefined;
}

function readValidatedRoomConfig(body: unknown): RoomConfiguration {
  if (!isRecord(body) || !isRecord(body.room_config)) {
    throw new Error("room_config is required");
  }

  const agents = body.room_config.agents;
  if (!Array.isArray(agents) || agents.length !== 1 || !isRecord(agents[0])) {
    throw new Error("room_config must contain one agent dispatch entry");
  }

  const requestedAgent = agents[0].agent_name;
  const requestedDeployment = agents[0].deployment;
  const requestedMetadata = agents[0].metadata;

  if (requestedAgent !== AGENT_NAME) {
    throw new Error("unsupported agent");
  }

  if (
    requestedDeployment !== undefined &&
    typeof requestedDeployment !== "string"
  ) {
    throw new Error("invalid deployment");
  }

  if (requestedMetadata !== undefined && typeof requestedMetadata !== "string") {
    throw new Error("invalid agent metadata");
  }

  const deployment = expectedDeployment();
  if (requestedDeployment !== deployment) {
    throw new Error("deployment does not match this environment");
  }

  const dispatch = new RoomAgentDispatch({
    agentName: AGENT_NAME,
    ...(deployment ? { deployment } : {}),
    ...(requestedMetadata ? { metadata: requestedMetadata } : {}),
  });

  return new RoomConfiguration({ agents: [dispatch] });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const roomConfig = readValidatedRoomConfig(body);

    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;
    const serverUrl = process.env.LIVEKIT_URL;

    if (!apiKey || !apiSecret || !serverUrl) {
      return NextResponse.json(
        { error: "LiveKit server configuration is incomplete" },
        { status: 500 },
      );
    }

    const accessToken = new AccessToken(apiKey, apiSecret, {
      identity: `voiceforce-user-${crypto.randomUUID()}`,
      name: "VoiceForce visitor",
      ttl: TOKEN_TTL,
    });

    accessToken.addGrant({
      roomJoin: true,
      room: `voiceforce-${crypto.randomUUID()}`,
      canPublish: true,
      canSubscribe: true,
    });
    accessToken.roomConfig = roomConfig;

    return NextResponse.json(
      {
        server_url: serverUrl,
        participant_token: await accessToken.toJwt(),
      },
      { status: 201 },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "invalid request";

    return NextResponse.json({ error: message }, { status: 400 });
  }
}
