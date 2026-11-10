from __future__ import annotations

from pathlib import Path

from scripts.summarize_latency import build_report, filter_records


def test_filter_keeps_one_session_and_room_correlation_only() -> None:
    records = [
        {
            "record_type": "metric",
            "session_id": "job-1",
            "labels": {"room_name": "console"},
            "metric": "e2e_latency",
            "value": 1.0,
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-2",
            "labels": {"room_name": "console"},
            "metric": "e2e_latency",
            "value": 2.0,
            "available": True,
        },
    ]

    filtered = filter_records(records, session_ids={"job-1"})

    assert len(filtered) == 1
    assert filtered[0]["value"] == 1.0


def test_report_separates_component_and_turn_metrics_and_preserves_missing() -> None:
    records = [
        {
            "record_type": "metric",
            "session_id": "job-1",
            "turn_id": "turn-1",
            "speech_id": "speech-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 2.0,
            "source": "conversation_item.metrics",
            "stage": "agent_turn",
            "metric": "e2e_latency",
            "value": 1.0,
            "unit": "seconds",
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-1",
            "speech_id": "speech-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 1.0,
            "source": "llm.metrics_collected",
            "stage": "llm",
            "metric": "llm_ttft",
            "value": 0.4,
            "unit": "seconds",
            "available": True,
        },
        {
            "record_type": "metric",
            "session_id": "job-1",
            "turn_id": "turn-1",
            "clock_domain": "backend_process",
            "monotonic_seconds": 3.0,
            "source": "conversation_item.metrics",
            "stage": "agent_turn",
            "metric": "tts_node_ttfb",
            "value": None,
            "unit": "seconds",
            "available": False,
            "missing_reason": "not exposed",
        },
    ]

    report = build_report(
        records,
        files=[Path("backend/data/latency_metrics.jsonl")],
        filters={"session_id": ["job-1"]},
        include_diagnostics=True,
    )

    assert report["session_ids"] == ["job-1"]
    assert report["metrics_by_scope"]["per_turn"]["e2e_latency"]["count"] == 1
    assert report["metrics_by_scope"]["per_component"]["llm_ttft"]["count"] == 1
    assert report["observation_counts"]["tts_node_ttfb"] == {
        "available": 0,
        "missing": 1,
        "total": 1,
    }
    diagnostic = next(
        item for item in report["turn_diagnostics"] if item["turn_id"] == "turn-1"
    )
    assert diagnostic["metrics"]["e2e_latency"] == 1.0
    assert diagnostic["metrics"]["tts_node_ttfb"] is None
    assert "llm_request_start" in diagnostic["missing_stages"]
