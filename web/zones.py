"""The user's time zone, as the browser sends it (`?tz=Europe/Madrid`)."""

from datetime import tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_tz(value: str | None) -> tzinfo | None:
    """The `tz` query parameter: an IANA zone name ("Europe/Madrid") or nothing (the caller's
    default zone). ValueError for anything else."""
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown time zone {value!r}") from e
