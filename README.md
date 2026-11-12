# fleet-telemetry-pipeline

A small, dependency-free Python pipeline that turns raw vehicle and equipment telemetry into data an operations team can trust: validated events, de-duplicated and ordered per asset, trip metrics, and alerts.

It reflects the problems I worked on when bringing equipment and site telemetry from fifteen industrial sites into one platform: events arriving late or twice, bad coordinates, gaps in coverage, and supervisors who need a short list of things to act on.

> Portfolio project (2026) by Fleury-Bryan Havyarimana. Written from scratch; no client code or data.

## What it does

| Step | Behaviour |
|---|---|
| Validate | Required fields, coordinate and speed ranges, ISO-8601 or epoch timestamps normalized to UTC |
| De-duplicate | Drops repeated `event_id`s (at-least-once delivery from Kafka, MQTT or Kinesis) |
| Order | Sorts each asset's events by time before computing anything |
| Summarize | Distance (haversine), engine minutes, idle minutes, max speed, data gaps |
| Alert | Speeding, idling past a threshold (once per idle run), coolant over-temperature |

Gaps longer than `max_gap_minutes` break accumulation, so a lost connection never turns into a fake 40 km "trip".

## Run it

```bash
python -m telemetry.cli sample/events.jsonl
python -m telemetry.cli sample/events.jsonl --speed-limit 90 --idle-minutes 5
```

Sample output (abridged):

```json
{
  "clean_events": 60,
  "duplicates": 1,
  "rejected": [{"reason": "bad value: Invalid isoformat string: 'not-a-date'", "event_id": "bad-1"}],
  "assets": [{"asset_id": "loader-07", "distance_km": 17.298, "idle_minutes": 18.0, "...": "..."}],
  "alerts": [{"asset_id": "loader-07", "kind": "idle", "detail": "idling 10 min"}, {"asset_id": "truck-101", "kind": "speeding"}, {"asset_id": "loader-07", "kind": "overheat"}]
}
```

## Use it as a library

```python
from telemetry import run, Rules

result = run(raw_events, Rules(speed_limit_kph=90, idle_alert_minutes=5))
for alert in result.alerts:
    print(alert.asset_id, alert.kind, alert.detail)
```

## Tests

```bash
pip install pytest
pytest -q
```

All 7 tests pass on Python 3.11.

## Design notes

- Storage-agnostic: the pipeline takes any iterable, so the same code sits behind a Kafka consumer, an MQTT subscriber or a batch file job.
- Rejected events keep their reason, so data owners can fix the source instead of losing data silently.
- Thresholds live in one `Rules` object that operations can tune per site.
