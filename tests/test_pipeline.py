from datetime import datetime, timedelta, timezone

import pytest

from telemetry.models import TelemetryEvent, ValidationError
from telemetry.pipeline import Rules, haversine_km, run

T0 = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)


def ev(i, asset="truck-1", minutes=0, lat=45.5, lon=-73.6, speed=0.0, engine=True, **extra):
    d = {"event_id": f"{asset}-{i}", "asset_id": asset, "ts": (T0 + timedelta(minutes=minutes)).isoformat(),
         "lat": lat, "lon": lon, "speed_kph": speed, "engine_on": engine}
    d.update(extra)
    return d


def test_validation_rejects_missing_and_out_of_range():
    with pytest.raises(ValidationError):
        TelemetryEvent.from_raw({"event_id": "x"})
    with pytest.raises(ValidationError):
        TelemetryEvent.from_raw(ev(1, lat=123))
    with pytest.raises(ValidationError):
        TelemetryEvent.from_raw(ev(1, speed=-5))


def test_timestamps_are_normalized_to_utc():
    e = TelemetryEvent.from_raw(ev(1) | {"ts": "2026-03-02T03:00:00-05:00"})
    assert e.ts == T0
    assert e.ts.utcoffset() == timedelta(0)


def test_duplicates_and_rejections_are_counted():
    r = run([ev(1), ev(1), {"event_id": "bad"}])
    assert r.duplicates == 1
    assert len(r.rejected) == 1
    assert len(r.clean) == 1


def test_out_of_order_events_are_sorted_before_distance():
    events = [ev(2, minutes=2, lat=45.51, speed=40), ev(1, minutes=0, lat=45.50, speed=40), ev(3, minutes=4, lat=45.52, speed=40)]
    r = run(events)
    s = r.summaries["truck-1"]
    assert [e.event_id for e in r.clean] == ["truck-1-1", "truck-1-2", "truck-1-3"]
    assert s.distance_km == pytest.approx(haversine_km(45.50, -73.6, 45.52, -73.6), rel=1e-3)


def test_idle_alert_fires_once_per_idle_run():
    events = [ev(i, minutes=i * 2, speed=0) for i in range(8)]  # 14 minutes idling
    r = run(events, Rules(idle_alert_minutes=10))
    idle = [a for a in r.alerts if a.kind == "idle"]
    assert len(idle) == 1
    assert r.summaries["truck-1"].idle_minutes == 14.0


def test_speeding_and_overheat_alerts():
    r = run([ev(1, speed=120), ev(2, minutes=1, speed=50, coolant_c=110)], Rules(speed_limit_kph=100))
    kinds = sorted(a.kind for a in r.alerts)
    assert kinds == ["overheat", "speeding"]


def test_gaps_break_accumulation():
    r = run([ev(1, minutes=0, speed=30), ev(2, minutes=60, lat=46.0, speed=30)])
    s = r.summaries["truck-1"]
    assert s.data_gaps == 1
    assert s.distance_km == 0.0
