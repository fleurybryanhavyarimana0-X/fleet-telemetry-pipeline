"""Event model and validation for vehicle and equipment telemetry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

REQUIRED_FIELDS = ("event_id", "asset_id", "ts", "lat", "lon", "speed_kph", "engine_on")


class ValidationError(ValueError):
    """Raised when a raw event cannot be turned into a TelemetryEvent."""


@dataclass(frozen=True)
class TelemetryEvent:
    event_id: str
    asset_id: str
    ts: datetime
    lat: float
    lon: float
    speed_kph: float
    engine_on: bool
    coolant_c: float | None = None
    site: str | None = None

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "TelemetryEvent":
        missing = [f for f in REQUIRED_FIELDS if f not in raw or raw[f] is None]
        if missing:
            raise ValidationError(f"missing fields: {', '.join(missing)}")
        try:
            ts = _parse_ts(raw["ts"])
            lat = float(raw["lat"])
            lon = float(raw["lon"])
            speed = float(raw["speed_kph"])
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"bad value: {exc}") from exc
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValidationError(f"coordinates out of range: {lat},{lon}")
        if speed < 0 or speed > 250:
            raise ValidationError(f"speed out of range: {speed}")
        coolant = raw.get("coolant_c")
        return cls(
            event_id=str(raw["event_id"]),
            asset_id=str(raw["asset_id"]),
            ts=ts,
            lat=lat,
            lon=lon,
            speed_kph=speed,
            engine_on=_parse_bool(raw["engine_on"]),
            coolant_c=float(coolant) if coolant is not None else None,
            site=raw.get("site"),
        )


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise ValidationError(f"not a boolean: {value!r}")
