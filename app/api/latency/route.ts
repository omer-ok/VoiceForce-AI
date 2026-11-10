import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

const MAX_RECORDS_PER_REQUEST = 32;
const MAX_REQUEST_BYTES = 64 * 1024;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBrowserMetric(value: unknown): value is Record<string, unknown> {
  return (
    isRecord(value) &&
    value.record_type === "metric" &&
    value.source === "browser.livekit_client" &&
    typeof value.session_id === "string" &&
    value.session_id.length <= 256 &&
    typeof value.stage === "string" &&
    value.stage.length <= 80 &&
    typeof value.metric === "string" &&
    value.metric.length <= 120 &&
    typeof value.unit === "string" &&
    value.unit.length <= 40
  );
}

export async function POST(request: Request) {
  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_REQUEST_BYTES) {
    return NextResponse.json({ error: "telemetry payload is too large" }, { status: 413 });
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return NextResponse.json({ error: "invalid telemetry JSON" }, { status: 400 });
  }

  const records = Array.isArray(parsed) ? parsed : [parsed];
  if (
    records.length === 0 ||
    records.length > MAX_RECORDS_PER_REQUEST ||
    records.some((record) => !isBrowserMetric(record))
  ) {
    return NextResponse.json({ error: "invalid telemetry record" }, { status: 400 });
  }

  const dataDirectory = path.join(process.cwd(), "data");
  const outputPath = path.join(dataDirectory, "latency_metrics.browser.jsonl");
  await mkdir(dataDirectory, { recursive: true });
  await appendFile(
    outputPath,
    records.map((record) => `${JSON.stringify(record)}\n`).join(""),
    "utf8",
  );

  return new NextResponse(null, { status: 204 });
}
