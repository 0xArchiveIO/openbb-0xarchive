"""Turn a registry command and a validated query into rows."""

import asyncio
import keyword
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.utils.errors import EmptyDataError, UnauthorizedError

from openbb_oxarchive.registry import COMMANDS
from openbb_oxarchive.utils.helpers import BASE_URL, normalize_symbol, to_timestamp

VENUE_PATHS: dict[str, str] = {
    "hyperliquid": "/v1/hyperliquid",
    "lighter": "/v1/lighter",
    "hip3": "/v1/hyperliquid/hip3",
    "hip4": "/v1/hyperliquid/hip4",
    "spot": "/v1/hyperliquid/spot",
    "rh-lighter": "/v1/rh-lighter",
}

# Query fields the engine handles itself rather than passing through.
RESERVED = {"venue", "limit", "start_date", "end_date"}
# Short venue field names spelled out for tables.
RENAMES = {"px": "price", "sz": "size", "n": "orders"}
TIME_KEYS = ("timestamp", "snapshot_ts", "calculated_at", "window_end", "first_seen_at")
# Default candle range when no start date is given, by interval.
CANDLE_LOOKBACK_DAYS = {"1m": 1, "5m": 3, "15m": 7, "30m": 14}
RETRIES = 5


class _Retry(Exception):
    """A rate limit or temporary server error worth retrying."""

    def __init__(self, message: str, wait: float | None):
        super().__init__(message)
        self.wait = wait


def command_url(key: str, venue: str, args: dict[str, str]) -> str:
    """Return the full route for one command, venue and set of path arguments."""
    venues = COMMANDS[key]["venues"]
    if venue not in venues:
        offered = ", ".join(venues)
        raise OpenBBError(f"This dataset is not offered for venue '{venue}'. Choose one of: {offered}.")
    path = venues[venue].format(**{name: quote(str(value), safe="") for name, value in args.items()})
    return f"{BASE_URL}{VENUE_PATHS[venue]}{path}"


def build_request(key: str, query: Any, venue: str) -> tuple[str, dict[str, Any]]:
    """Return the URL and query string for a validated query."""
    cfg = COMMANDS[key]
    values = query.model_dump() if hasattr(query, "model_dump") else dict(query)
    args = {}
    for name in cfg["args"]:
        value = values[name]
        args[name] = normalize_symbol(value) if name == "symbol" else str(value).strip()
    params: dict[str, Any] = {}
    for name, value in values.items():
        if name in RESERVED or name in cfg["args"] or value is None:
            continue
        if name == "interval" and value == "raw":
            continue
        params[name] = str(value).lower() if isinstance(value, bool) else value
    start, end = values.get("start_date"), values.get("end_date")
    if key == "candles" and start is None:
        # The API's own default is the last 24 hours, which is one daily candle.
        # Look back far enough to draw a chart, staying inside Free's 30-day window.
        days = CANDLE_LOOKBACK_DAYS.get(values.get("interval") or "1d", 29)
        anchor = datetime.fromisoformat(to_timestamp(end, end=True).replace("Z", "+00:00")) if end else datetime.now(timezone.utc)
        start = anchor - timedelta(days=days)
    if start is not None:
        params["start"] = to_timestamp(start)
    if end is not None:
        params["end"] = to_timestamp(end, end=True)
    return command_url(key, venue, args), params


def _flatten(row: dict, prefix: str = "") -> dict:
    """Flatten nested objects into ``parent_child`` columns."""
    out: dict = {}
    for name, value in row.items():
        column = f"{prefix}{name}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{column}_"))
        else:
            out[column] = value
    return out


def _as_time(value: Any) -> Any:
    """Read epoch milliseconds as a UTC datetime."""
    if isinstance(value, (int, float)) and value > 10**11:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return value


def shape_rows(key: str, data: Any) -> list[dict]:
    """Return flat rows for one page of ``data``."""
    cfg = COMMANDS[key]
    if cfg.get("rows") and isinstance(data, dict):
        data = data.get(cfg["rows"]) or []
    items = data if isinstance(data, list) else [data] if data else []
    explode = cfg.get("explode")
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not explode:
            rows.append(_flatten(item))
            continue
        parent = _flatten({k: v for k, v in item.items() if k not in explode})
        for field in explode:
            side = {"bids": "bid", "asks": "ask"}.get(field)
            for level, child in enumerate(item.get(field) or [], start=1):
                flat = _flatten(child) if isinstance(child, dict) else {"value": child}
                flat = {RENAMES.get(name, name): value for name, value in flat.items()}
                prefix = "order_" if ("oid" in flat or "order_index" in flat) else "level_"
                row = dict(parent)
                for name, value in flat.items():
                    row[f"{prefix}{name}" if name in row else name] = value
                if side:
                    row.setdefault("side", side)
                    row["level"] = level
                rows.append(row)
    for row in rows:
        for name in [n for n in row if keyword.iskeyword(n)]:
            row[f"{name}_"] = row.pop(name)
        if "coin" in row:
            row.setdefault("symbol", row["coin"])
            row.pop("coin")
        for name in TIME_KEYS:
            if name in row and "date" not in row:
                row["date"] = _as_time(row.pop(name))
                row.pop(f"{name}_ms", None)
                break
    return rows


async def _read(response, _session) -> dict:
    """Return the JSON body, turning an API error into an OpenBB error."""
    try:
        body = await response.json(content_type=None)
    except Exception as error:  # noqa: BLE001
        raise OpenBBError(f"0xArchive returned an unreadable response (HTTP {response.status}).") from error
    message = body.get("error") if isinstance(body, dict) else None
    if response.status == 429 or response.status >= 500:
        wait = None
        try:
            wait = float((getattr(response, "headers", None) or {}).get("Retry-After"))
        except (TypeError, ValueError):
            pass
        raise _Retry(message or f"0xArchive request failed (HTTP {response.status}).", wait)
    if response.status == 401:
        raise UnauthorizedError(message or "0xArchive rejected the API key. Check `oxarchive_api_key`.")
    if response.status == 403:
        raise OpenBBError(
            (message or "Your plan does not include this request.")
            + " Plans: https://0xarchive.io/pricing"
        )
    if response.status != 200 or not isinstance(body, dict) or body.get("success") is False:
        raise OpenBBError(message or f"0xArchive request failed (HTTP {response.status}).")
    return body


async def _fetch(amake_request, url: str, params: dict, headers: dict) -> dict:
    """Request one page, waiting and retrying on rate limits and server errors."""
    for attempt in range(RETRIES + 1):
        try:
            # No redirects: the API key header must only ever reach api.0xarchive.io.
            return await amake_request(
                url, params=params, headers=headers, response_callback=_read, timeout=60, allow_redirects=False
            )
        except _Retry as error:
            if attempt == RETRIES:
                raise OpenBBError(str(error)) from error
            await asyncio.sleep(min(error.wait if error.wait is not None else 2**attempt, 60))
    raise AssertionError("unreachable")


async def run(
    key: str,
    query: Any,
    credentials: dict[str, str] | None,
    page_max: int | None = None,
) -> list[dict]:
    """Fetch every page a query asks for and return flat rows."""
    from openbb_core.provider.utils.helpers import amake_request

    api_key = (credentials or {}).get("oxarchive_api_key")
    if not api_key:
        raise UnauthorizedError(
            "An 0xArchive API key is required. Create one at https://0xarchive.io and"
            " set it as `oxarchive_api_key`."
        )
    cfg = COMMANDS[key]
    venue = getattr(query, "venue", None) or next(iter(cfg["venues"]))
    url, params = build_request(key, query, venue)
    limit = getattr(query, "limit", None)
    paged = cfg.get("paged", True) and not cfg.get("single")
    headers = {"X-API-Key": api_key}
    raw: list[dict] = []
    rows: list[dict] = []
    cursor = cursor_seq = None

    while True:
        page = dict(params)
        if limit is not None:
            want = limit - len(raw)
            page["limit"] = min(page_max, want) if (paged and page_max) else limit
        if cursor:
            page["cursor"] = cursor
        if cursor_seq is not None:
            page["cursor_seq"] = cursor_seq
        body = await _fetch(amake_request, url, page, headers)
        data = body.get("data")
        batch = data if isinstance(data, list) else [data] if data is not None else []
        if cfg.get("rows") and isinstance(data, dict):
            batch = data.get(cfg["rows"]) or []
        raw.extend(batch)
        rows.extend(shape_rows(key, data))
        meta = body.get("meta") or {}
        previous = (cursor, cursor_seq)
        cursor = meta.get("next_cursor")
        cursor_seq = meta.get("next_cursor_seq", (data or {}).get("next_cursor_seq") if isinstance(data, dict) else None)
        if not paged or not meta.get("has_more") or not cursor or (cursor, cursor_seq) == previous or not batch:
            break
        if limit is not None and len(raw) >= limit:
            break

    if not rows:
        raise EmptyDataError("0xArchive returned no rows for this request.")
    if limit is not None and not cfg.get("explode"):
        rows = rows[:limit]
    return rows
