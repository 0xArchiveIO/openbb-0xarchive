"""Shared request and paging helpers for the 0xArchive provider."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal

BASE_URL = "https://api.0xarchive.io"

Venue = Literal["hyperliquid", "lighter", "hip3", "hip4", "spot", "rh-lighter"]
Interval = Literal["raw", "1m", "5m", "15m", "30m", "1h", "4h", "1d"]
CandleInterval = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]



SUFFIXES = ("-USDC", "-USDT", "-USD", "-PERP")


def normalize_symbol(symbol: str) -> str:
    """Map an OpenBB-style symbol to the 0xArchive form.

    ``BTC-USD`` becomes ``BTC``. A HIP-3 symbol keeps its lower-case
    deployer prefix, so ``XYZ:NVDA`` becomes ``xyz:NVDA``.
    """
    value = str(symbol).strip()
    upper = value.upper()
    for suffix in SUFFIXES:
        if upper.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if ":" in value:
        dex, coin = value.split(":", 1)
        return f"{dex.lower()}:{coin.upper()}"
    return value.upper()


def to_timestamp(value: Any, end: bool = False) -> str | None:
    """Return an RFC 3339 UTC timestamp. A bare end date includes that whole day."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    elif isinstance(value, date):
        moment = datetime.combine(value, time.min, tzinfo=timezone.utc)
        if end:
            moment += timedelta(days=1)
    else:
        text = str(value)
        if len(text) == 10:
            return to_timestamp(date.fromisoformat(text), end)
        return to_timestamp(datetime.fromisoformat(text.replace("Z", "+00:00")), end)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
