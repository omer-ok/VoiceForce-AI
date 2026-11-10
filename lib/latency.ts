"use client";

export type BrowserMetric = {
  stage: string;
  metric: string;
  value?: number | null;
  unit: string;
  labels?: Record<string, string | number | boolean | null | undefined>;
  available?: boolean;
  missing_reason?: string;
};

type BrowserMetricLabels = NonNullable<BrowserMetric["labels"]>;

export class BrowserLatencyRecorder {
  private readonly sessionId: string | (() => string);
  private readonly context:
    | (() => BrowserMetricLabels)
    | undefined;

  constructor(
    sessionId: string | (() => string),
    context?: () => BrowserMetricLabels,
  ) {
    this.sessionId = sessionId;
    this.context = context;
  }

  record(metric: BrowserMetric) {
    const sessionId =
      typeof this.sessionId === "function" ? this.sessionId() : this.sessionId;
    const valueAvailable =
      metric.available ?? (metric.value !== null && metric.value !== undefined);
    const contextLabels = this.context?.() ?? {};
    const labels = { ...contextLabels, ...(metric.labels ?? {}) };
    const record = {
      schema_version: 1,
      record_type: "metric",
      session_id: sessionId || "unknown",
      timestamp: new Date().toISOString(),
      monotonic_ms:
        typeof performance === "undefined" ? null : performance.now(),
      clock_domain: "browser_performance",
      source: "browser.livekit_client",
      stage: metric.stage,
      metric: metric.metric,
      value: metric.value ?? null,
      unit: metric.unit,
      available: valueAvailable,
      ...(Object.keys(labels).length > 0 ? { labels } : {}),
      ...(metric.missing_reason
        ? { missing_reason: metric.missing_reason }
        : {}),
    };

    const payload = JSON.stringify(record);
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const sent = navigator.sendBeacon(
        "/api/latency",
        new Blob([payload], { type: "application/json" }),
      );
      if (sent) {
        return;
      }
    }

    void fetch("/api/latency", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: payload,
      keepalive: true,
    }).catch(() => undefined);
  }
}
