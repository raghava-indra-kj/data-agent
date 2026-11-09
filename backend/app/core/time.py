import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    return datetime.now(UTC)


def validate_timezone(value: str) -> str:
    """Validate an IANA timezone, preserving supported aliases such as Asia/Calcutta."""
    if not re.fullmatch(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*", value):
        raise ValueError("Use a valid IANA timezone, such as Asia/Kolkata or UTC.")
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError, OSError) as exc:
        raise ValueError("Use a valid IANA timezone, such as Asia/Kolkata or UTC.") from exc
    return value


def clock_snapshot(timezone: str, *, now: datetime | None = None) -> dict[str, str]:
    instant = now if now is not None else utc_now()
    if instant.tzinfo is None:
        raise ValueError("Clock instants must include a timezone.")
    instant = instant.astimezone(UTC)
    local = instant.astimezone(ZoneInfo(validate_timezone(timezone)))
    offset = local.strftime("%z")
    return {
        "utc_timestamp": instant.isoformat(),
        "timezone": timezone,
        "local_timestamp": local.isoformat(),
        "local_date": local.date().isoformat(),
        "utc_offset": f"{offset[:3]}:{offset[3:]}",
    }
