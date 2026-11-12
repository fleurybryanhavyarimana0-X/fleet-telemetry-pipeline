"""Fleet telemetry ingestion: validation, de-duplication, trip metrics and alerts."""
from .models import TelemetryEvent, ValidationError
from .pipeline import Rules, run

__all__ = ["TelemetryEvent", "ValidationError", "Rules", "run"]
