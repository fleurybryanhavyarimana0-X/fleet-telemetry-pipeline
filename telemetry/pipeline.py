"""Ingestion pipeline: validate, de-duplicate, order and summarize telemetry.

The pipeline is deliberately storage-agnostic. It takes an iterable of raw
events (from Kafka, MQTT, Kinesis or a file) and returns clean events,
rejected events with reasons, per-asset summaries and alerts.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable, Mapping

from .models import TelemetryEvent, ValidationError


@dataclass
class Rules:
    speed_limit_kph: float = 100.0
    idle_alert_minutes: float = 10.0
    coolant_max_c: float = 105.0
    max_gap_minutes: float = 15.0


@dataclass
class Alert:
    asset_id: str
    kind: str
    at: str
    detail: str


@dataclass
class AssetSummary:
    asset_id: str
    events: int = 0
    distance_km: float = 0.0
    engine_minutes: float = 0.0
    idle_minutes: float = 0.0
    max_speed_kph: float = 0.0
    data_gaps: int = 0


@dataclass
class Result:
    clean: list[TelemetryEvent] = field(default_factory=list)
    rejected: list[tuple[Mapping[str, Any], str]] = field(default_factory=list)
    duplicates: int = 0
    summaries: dict[str, AssetSummary] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def run(raw_events: Iterable[Mapping[str, Any]], rules: Rules | None = None) -> Result:
    rules = rules or Rules()
    result = Result()
    seen: set[str] = set()
    by_asset: dict[str, list[TelemetryEvent]] = defaultdict(list)

    for raw in raw_events:
        try:
            event = TelemetryEvent.from_raw(raw)
        except ValidationError as exc:
            result.rejected.append((raw, str(exc)))
            continue
        if event.event_id in seen:
            result.duplicates += 1
            continue
        seen.add(event.event_id)
        by_asset[event.asset_id].append(event)

    for asset_id, events in by_asset.items():
        events.sort(key=lambda e: e.ts)
        result.clean.extend(events)
        summary, alerts = _summarize(asset_id, events, rules)
        result.summaries[asset_id] = summary
        result.alerts.extend(alerts)

    result.alerts.sort(key=lambda a: (a.at, a.asset_id))
    return result


def _summarize(asset_id: str, events: list[TelemetryEvent], rules: Rules) -> tuple[AssetSummary, list[Alert]]:
    s = AssetSummary(asset_id=asset_id, events=len(events))
    alerts: list[Alert] = []
    idle_run = timedelta(0)
    idle_alerted = False
    max_gap = timedelta(minutes=rules.max_gap_minutes)

    for prev, cur in zip(events, events[1:]):
        gap = cur.ts - prev.ts
        if gap > max_gap:
            s.data_gaps += 1
            idle_run, idle_alerted = timedelta(0), False
            continue
        minutes = gap.total_seconds() / 60
        s.distance_km += haversine_km(prev.lat, prev.lon, cur.lat, cur.lon)
        if prev.engine_on:
            s.engine_minutes += minutes
            if prev.speed_kph < 2:
                s.idle_minutes += minutes
                idle_run += gap
                if not idle_alerted and idle_run >= timedelta(minutes=rules.idle_alert_minutes):
                    alerts.append(Alert(asset_id, "idle", cur.ts.isoformat(), f"idling {idle_run.total_seconds() / 60:.0f} min"))
                    idle_alerted = True
            else:
                idle_run, idle_alerted = timedelta(0), False

    for e in events:
        s.max_speed_kph = max(s.max_speed_kph, e.speed_kph)
        if e.speed_kph > rules.speed_limit_kph:
            alerts.append(Alert(asset_id, "speeding", e.ts.isoformat(), f"{e.speed_kph:.0f} kph > {rules.speed_limit_kph:.0f}"))
        if e.coolant_c is not None and e.coolant_c > rules.coolant_max_c:
            alerts.append(Alert(asset_id, "overheat", e.ts.isoformat(), f"coolant {e.coolant_c:.0f} C"))

    s.distance_km = round(s.distance_km, 3)
    s.engine_minutes = round(s.engine_minutes, 1)
    s.idle_minutes = round(s.idle_minutes, 1)
    return s, alerts
