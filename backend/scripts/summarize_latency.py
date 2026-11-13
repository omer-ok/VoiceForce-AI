"""Summarize isolated VoiceForce backend and browser latency JSONL records."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from voiceforce_agent.latency_metrics import (
    aggregate_metric_records,
    default_metrics_path,
    read_jsonl,
)

_TURN_METRICS = {
    "e2e_latency": "e2e_latency",
    "end_of_turn_delay": "eou_delay",
    "transcription_delay": "transcription_delay",
    "llm_node_ttft": "llm_node_ttft",
    "llm_node_ttfs": "llm_node_ttfs",
    "tts_node_ttfb": "tts_node_ttfb",
    "playback_latency": "agent_playback_latency",
    "tool_execution_duration": "tool_duration",
    "database_connection_duration": "database_connection_duration",
    "sql_execution_duration": "sql_execution_duration",
    "database_query_duration": "database_query_duration",
    "speech_interrupted": "speech_interrupted",
    "slow_response": "slow_response",
    "caller_speech_end_to_remote_signal": "caller_speech_end_to_remote_signal",
}

_REQUIRED_STAGES = {
    "end_of_user_speech": ("stopped_speaking_at",),
    "final_transcript_availability": ("final_transcript_received",),
    "end_of_turn_decision": ("eou_delay",),
    "llm_request_start": ("llm_request_started",),
    "llm_first_token": ("llm_node_ttft",),
    "first_sentence_to_tts": ("first_sentence_to_tts",),
    "tts_request_start": ("tts_request_started",),
    "tts_first_audio_chunk": ("tts_node_ttfb",),
    "first_audio_frame_forwarded": ("first_audio_frame_forwarded",),
    "browser_remote_track_subscription": ("subscribed",),
    "html_audio_playback_start": ("playing",),
}


def filter_records(
    records: Iterable[Mapping[str, Any]],
    *,
    session_ids: set[str] | None = None,
    turn_ids: set[str] | None = None,
    speech_ids: set[str] | None = None,
    room_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter by session, then retain records linked to selected turn/speech IDs."""

    selected: list[dict[str, Any]] = []
    for record in records:
        if session_ids and str(record.get("session_id")) not in session_ids:
            continue
        if room_names:
            labels = record.get("labels")
            report = record.get("report")
            record_room = labels.get("room_name") if isinstance(labels, Mapping) else None
            report_room = report.get("room") if isinstance(report, Mapping) else None
            if record_room not in room_names and report_room not in room_names:
                continue
        selected.append(dict(record))
    if turn_ids or speech_ids:
        by_node: defaultdict[tuple[str, str, str, str], list[int]] = defaultdict(list)
        for index, record in enumerate(selected):
            for node in _correlation_nodes(record):
                by_node[node].append(index)
        pending = [
            index for index, record in enumerate(selected)
            if (not turn_ids or str(record.get("turn_id")) in turn_ids)
            and (not speech_ids or str(record.get("speech_id")) in speech_ids)
        ]
        included = set(pending)
        visited: set[tuple[str, str, str, str]] = set()
        while pending:
            index = pending.pop()
            for node in _correlation_nodes(selected[index]):
                if node in visited:
                    continue
                visited.add(node)
                for linked in by_node[node]:
                    if linked not in included:
                        included.add(linked)
                        pending.append(linked)
        selected = [record for index, record in enumerate(selected) if index in included]
    return selected


def metric_scope(record: Mapping[str, Any]) -> str:
    """Classify granularity so component and per-turn values are not conflated."""

    source = str(record.get("source", ""))
    if source == "conversation_item.metrics":
        return "per_turn"
    if source.endswith(".metrics_collected"):
        return "per_component"
    if source.startswith("browser."):
        return "browser_event"
    if record.get("stage") == "tool":
        return "tool"
    return "event"


def aggregate_by_scope(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    scoped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        scoped[metric_scope(record)].append(record)
    return {
        scope: aggregate_metric_records(scope_records)
        for scope, scope_records in sorted(scoped.items())
    }


def observation_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {
        name: {"available": 0, "missing": 0, "total": 0}
        for name in _TURN_METRICS
    }
    aliases = {raw: public for public, raw in _TURN_METRICS.items()}
    for record in records:
        if record.get("record_type", "metric") != "metric":
            continue
        public_name = aliases.get(str(record.get("metric")))
        if public_name is None:
            continue
        item = counts[public_name]
        item["total"] += 1
        if record.get("available") is False or record.get("value") is None:
            item["missing"] += 1
        else:
            item["available"] += 1
    return counts


def _timeline_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "timestamp",
            "monotonic_seconds",
            "monotonic_ms",
            "clock_domain",
            "stage",
            "metric",
            "value",
            "unit",
            "available",
            "missing_reason",
            "source",
            "session_id",
            "turn_id",
            "speech_id",
            "request_id",
            "labels",
        )
        if key in record
    }


def _turn_key(record: Mapping[str, Any]) -> tuple[str, str | None]:
    turn_id = record.get("turn_id")
    speech_id = record.get("speech_id")
    if turn_id:
        return (f"turn:{turn_id}", None)
    if speech_id:
        return (f"speech:{speech_id}", str(speech_id))
    return ("unlinked", None)


def _correlation_nodes(record: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    session = str(record.get("session_id") or "unknown")
    clock = str(record.get("clock_domain") or "unknown")
    fields = [("turn", record.get("turn_id")), ("speech", record.get("speech_id"))]
    if record.get("stage") == "tool" or record.get("metric") == "speech_tool_link":
        fields.append(("call", record.get("request_id")))
    labels = record.get("labels")
    if isinstance(labels, Mapping):
        if record.get("metric") == "fast_property_reply_scheduled":
            fields.append(("speech", labels.get("reply_speech_id")))
        elif record.get("metric") == "search_acknowledgement_requested":
            fields.append(("speech", labels.get("acknowledgement_speech_id")))
    return [(session, clock, kind, str(value)) for kind, value in fields if value]


def build_turn_diagnostics(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build diagnostics only from explicit IDs; never infer cross-domain turns."""

    items = [
        record for record in records if record.get("record_type", "metric") == "metric"
    ]
    parents: dict[tuple[str, str, str, str], tuple[str, str, str, str]] = {}

    def root(node: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
        parents.setdefault(node, node)
        while parents[node] != node:
            node = parents[node]
        return node

    for record in items:
        identifiers = _correlation_nodes(record)
        if identifiers:
            first = root(identifiers[0])
            for other in identifiers[1:]:
                parents[root(other)] = root(first)

    grouped_records: defaultdict[tuple[str, str, str, str], list[Mapping[str, Any]]] = (
        defaultdict(list)
    )
    for record in items:
        identifiers = _correlation_nodes(record)
        if identifiers:
            grouped_records[root(identifiers[0])].append(record)

    diagnostics: list[dict[str, Any]] = []
    for root_id, grouped in sorted(grouped_records.items()):
        turn_ids = list(
            dict.fromkeys(
                record.get("turn_id")
                for record in grouped
                if record.get("turn_id") and record.get("stage") == "agent_turn"
            )
        )
        if not turn_ids:
            turn_ids = [
                next(
                    (
                        record.get("turn_id")
                        for record in grouped
                        if record.get("turn_id")
                    ),
                    None,
                )
            ]
        for turn_id in turn_ids:
            turn_records = [
                record
                for record in grouped
                if not record.get("turn_id") or record.get("turn_id") == turn_id
            ]
            diagnostics.append(
                _build_diagnostic(root_id, grouped, turn_records, turn_id)
            )
    return diagnostics


def _build_diagnostic(
    root_id: tuple[str, str, str, str],
    grouped: list[Mapping[str, Any]],
    turn_records: list[Mapping[str, Any]],
    turn_id: Any,
) -> dict[str, Any]:
    speech_id = next(
        (
            str(record.get("speech_id"))
            for record in grouped
            if record.get("turn_id") == turn_id and record.get("speech_id")
        ),
        next(
            (
                str(record.get("speech_id"))
                for record in grouped
                if record.get("speech_id")
            ),
            None,
        ),
    )
    key = (
        f"turn:{turn_id}"
        if turn_id
        else f"speech:{speech_id}"
        if speech_id
        else f"call:{root_id[3]}"
    )
    available_metrics: dict[str, Any] = {}
    for record in turn_records:
        if record.get("available") is not False and record.get("value") is not None:
            available_metrics[str(record.get("metric"))] = record.get("value")

    stages: dict[str, dict[str, Any]] = {}
    for stage, metric_names in _REQUIRED_STAGES.items():
        match = next(
            (
                record
                for record in turn_records
                if record.get("metric") in metric_names
                and record.get("available") is not False
                and record.get("value") is not None
            ),
            None,
        )
        if match is None:
            stages[stage] = {"available": False, "value": None}
        else:
            stages[stage] = {
                "available": True,
                "value": match.get("value"),
                "unit": match.get("unit"),
                "source": match.get("source"),
                "measurement": "duration"
                if match.get("metric") in _TURN_METRICS.values()
                else "event_or_timestamp",
            }

    return {
        "key": key,
        "session_id": root_id[0],
        "clock_domain": root_id[1],
        "turn_id": turn_id,
        "speech_id": speech_id,
        "metrics": {
            public_name: available_metrics.get(raw_name)
            for public_name, raw_name in _TURN_METRICS.items()
        },
        "stages": stages,
        "missing_stages": [
            stage for stage, result in stages.items() if not result["available"]
        ],
        "backend_timeline": [
            _timeline_record(record)
            for record in sorted(
                grouped,
                key=lambda record: float(record.get("monotonic_seconds", 0.0)),
            )
            if record.get("clock_domain") == "backend_process"
        ],
        "browser_timeline": [
            _timeline_record(record)
            for record in sorted(
                grouped,
                key=lambda record: float(record.get("monotonic_ms", 0.0)),
            )
            if record.get("clock_domain") == "browser_performance"
        ],
    }


def build_report(
    records: list[Mapping[str, Any]],
    *,
    files: list[Path],
    filters: Mapping[str, list[str]],
    include_diagnostics: bool,
) -> dict[str, Any]:
    session_ids = sorted({str(record.get("session_id")) for record in records})
    record_types = Counter(str(record.get("record_type", "metric")) for record in records)
    report: dict[str, Any] = {
        "files": [str(path) for path in files],
        "filters": dict(filters),
        "records": len(records),
        "record_types": dict(sorted(record_types.items())),
        "session_count": len(session_ids),
        "session_ids": session_ids,
        "clock_domains": sorted({str(record.get("clock_domain")) for record in records}),
        "observation_counts": observation_counts(records),
        "metrics": aggregate_metric_records(records),
        "metrics_by_scope": aggregate_by_scope(records),
        "slow_responses": [
            _timeline_record(record)
            for record in records
            if record.get("metric") == "slow_response"
            and record.get("available") is not False
        ],
    }
    if include_diagnostics:
        report["turn_diagnostics"] = build_turn_diagnostics(records)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        help="JSONL file to summarize; may be provided more than once",
    )
    parser.add_argument("--session-id", action="append", help="include only this session ID")
    parser.add_argument("--turn-id", action="append", help="include only this turn ID")
    parser.add_argument("--speech-id", action="append", help="include only this speech ID")
    parser.add_argument(
        "--room-name",
        action="append",
        help="include records labeled with this LiveKit room name",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="include chronological per-turn diagnostics and missing stages",
    )
    args = parser.parse_args()
    paths = args.input or [default_metrics_path()]
    all_records = [record for path in paths for record in read_jsonl(path)]
    filters = {
        "session_id": args.session_id or [],
        "turn_id": args.turn_id or [],
        "speech_id": args.speech_id or [],
        "room_name": args.room_name or [],
    }
    records = filter_records(
        all_records,
        session_ids=set(args.session_id or []),
        turn_ids=set(args.turn_id or []),
        speech_ids=set(args.speech_id or []),
        room_names=set(args.room_name or []),
    )
    print(
        json.dumps(
            build_report(
                records,
                files=paths,
                filters=filters,
                include_diagnostics=args.diagnostic
                or bool(args.session_id or args.turn_id or args.speech_id),
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
