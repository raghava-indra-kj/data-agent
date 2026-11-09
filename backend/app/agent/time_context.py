from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.time import clock_snapshot, utc_now, validate_timezone


@dataclass(frozen=True, slots=True)
class RequestTimeContext:
    """Durable reference for one question; current clock readings are not persisted here."""

    reference_at: datetime
    timezone: str = "UTC"
    timezone_source: str = "default"

    def to_metadata(self) -> dict[str, str]:
        if self.reference_at.tzinfo is None:
            raise ValueError("The question reference must include a timezone.")
        return {
            "reference_at": self.reference_at.astimezone(UTC).isoformat(),
            "timezone": validate_timezone(self.timezone),
            "timezone_source": self.timezone_source,
        }

    @classmethod
    def from_metadata(cls, value: object, *, fallback_at: datetime) -> RequestTimeContext:
        # Legacy jobs use their original creation time, stable across worker retries.
        if isinstance(value, dict):
            try:
                reference = datetime.fromisoformat(str(value["reference_at"]))
                timezone = validate_timezone(str(value["timezone"]))
                if reference.tzinfo is not None:
                    return cls(reference, timezone, str(value.get("timezone_source", "default")))
            except (KeyError, TypeError, ValueError):
                pass
        if fallback_at.tzinfo is None:
            fallback_at = fallback_at.replace(tzinfo=UTC)
        return cls(fallback_at)


def render_time_context(
    context: RequestTimeContext | None = None, *, now: datetime | None = None
) -> str:
    instant = now if now is not None else utc_now()
    context = context or RequestTimeContext(instant)
    data = {
        "current": clock_snapshot(context.timezone, now=instant),
        "question_reference": clock_snapshot(context.timezone, now=context.reference_at),
        "timezone_source": context.timezone_source,
    }
    return """# Server time context

These timestamps come from the application server clock. UTC is the fallback when no user
timezone was supplied (timezone_source=default); do not claim it is the user's local timezone.
Interpret relative analytical periods (today, yesterday, last month, this year) using
question_reference and its timezone. Preserve that reference across retries and clarifications.
Explicit dates, timezone requests, and established conversation periods take precedence.
For a direct question about the current date/time, use current, or call get_current_time for a
fresh reading or another timezone. A clock reading does not change the question_reference.
For a clock-only question, answer from these facts; datasource discovery and SQL are unnecessary.
Verify database timestamp conventions and fiscal calendars from source knowledge; do not infer
them from the user timezone. Use explicit date boundaries in queries. Clock time does not prove
data freshness. Runtime clock facts support date/time answers only, never business metrics.

""" + json.dumps(data, ensure_ascii=False)


def is_time_only_question(question: str) -> bool:
    """Conservative exemption for whole clock questions, never analytical requests."""
    text = re.sub(r"\s+", " ", question.strip()).rstrip("?.!").strip()
    parts = re.split(r" in ", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        try:
            validate_timezone(parts[1])
        except ValueError:
            return False
        text = parts[0]
    return bool(
        re.fullmatch(
            r"(?:please )?(?:"
            r"what(?:'s| is| are) (?:the )?(?:current |local |today's )?"
            r"(?:date(?: and (?:the )?time)?|time(?: and (?:the )?date)?|day)"
            r"(?: (?:today|now))?"
            r"|what (?:time|date|day) is it(?: (?:today|now))?"
            r"|(?:tell me|show me|give me) (?:the )?(?:current |local )?"
            r"(?:date(?: and time)?|time(?: and date)?)"
            r")",
            text,
            flags=re.IGNORECASE,
        )
    )
