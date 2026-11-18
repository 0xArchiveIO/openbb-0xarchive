"""Offline tests. No request leaves the process."""

from datetime import date, datetime, timezone

import pytest
from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.utils.errors import EmptyDataError, UnauthorizedError

from openbb_oxarchive import oxarchive_provider
from openbb_oxarchive.models import generated as g
from openbb_oxarchive.models.crypto_historical import OxarchiveCryptoHistoricalFetcher
from openbb_oxarchive.models.standard import OxarchiveCryptoSearchFetcher
from openbb_oxarchive.registry import COMMANDS
from openbb_oxarchive.utils.helpers import normalize_symbol, to_timestamp

CREDS = {"oxarchive_api_key": "test-key"}


class Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self, **_):
        return self._body


@pytest.fixture
def api(monkeypatch):
    """Serve canned pages and record every request."""
    calls = []

    def install(pages):
        calls.clear()

        async def fake(url, response_callback=None, **kwargs):
            calls.append({"url": url, **kwargs})
            status, body = pages[min(len(calls), len(pages)) - 1]
            return await response_callback(Response(status, body), None)

        monkeypatch.setattr("openbb_core.provider.utils.helpers.amake_request", fake)
        return calls

    return install


def page(data, cursor=None):
    return 200, {"success": True, "data": data, "meta": {"has_more": cursor is not None, "next_cursor": cursor}}


CANDLE = {"timestamp": "2026-11-18T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0, "trade_count": 7}
BOOK = {
    "symbol": "BTC",
    "coin": "BTC",
    "timestamp": "2026-11-18T18:35:21Z",
    "bids": [{"px": "100", "sz": "2", "n": 3}, {"px": "99", "sz": "1", "n": 1}],
    "asks": [{"px": "101", "sz": "4", "n": 2}],
    "mid_price": "100.5",
    "spread": "1",
}


def test_every_command_is_registered():
    names = set(oxarchive_provider.fetcher_dict)
    assert {"CryptoHistorical", "CryptoSearch", "FuturesHistorical", "FuturesInstruments"} <= names
    assert len(g.FETCHERS) == len(COMMANDS)
    assert set(g.FETCHERS) <= names


def test_symbols_and_timestamps():
    assert normalize_symbol("btc-usd") == "BTC"
    assert normalize_symbol("XYZ:NVDA") == "xyz:NVDA"
    assert normalize_symbol("#398031") == "#398031"
    assert to_timestamp(date(2026, 1, 1), end=True) == "2026-01-02T00:00:00Z"
    assert to_timestamp(datetime(2026, 1, 1, 12, tzinfo=timezone.utc)) == "2026-01-01T12:00:00Z"


async def test_candles_route_and_paging(api):
    calls = api([page([CANDLE] * 3, cursor="c1"), page([CANDLE] * 3, cursor="c2")])
    rows = await OxarchiveCryptoHistoricalFetcher.fetch_data(
        {"symbol": "XYZ:NVDA", "venue": "hip3", "start_date": "2026-11-01", "limit": 5}, CREDS
    )
    assert calls[0]["url"].endswith("/v1/hyperliquid/hip3/candles/xyz%3ANVDA")
    assert calls[0]["headers"] == {"X-API-Key": "test-key"}
    assert calls[0]["params"]["start"] == "2026-11-01T00:00:00Z"
    assert calls[1]["params"]["cursor"] == "c1" and calls[1]["params"]["limit"] == 2
    assert len(rows) == 5 and rows[0].close == 1.5


async def test_book_is_one_row_per_level(api):
    calls = api([page(BOOK)])
    rows = await g.OxarchiveBookFetcher.fetch_data({"symbol": "BTC", "venue": "lighter"}, CREDS)
    assert calls[0]["url"].endswith("/v1/lighter/orderbook/BTC")
    dumped = [r.model_dump() for r in rows]
    assert [(r["side"], r["level"], r["price"]) for r in dumped] == [("bid", 1, 100.0), ("bid", 2, 99.0), ("ask", 1, 101.0)]
    assert "coin" not in dumped[0] and dumped[0]["orders"] == 3


async def test_l4_order_fields_do_not_clobber_snapshot(api):
    snap = {"coin": "BTC", "timestamp": "2026-11-18T00:00:00Z", "bids": [{"oid": 1, "user_address": "0xabc", "side": "B", "price": 100.0, "size": 1.0, "timestamp": "2026-11-17T00:00:00Z"}], "asks": []}
    api([page(snap)])
    rows = await g.OxarchiveBookL4Fetcher.fetch_data({"symbol": "BTC"}, CREDS)
    dumped = rows[0].model_dump()
    assert dumped["oid"] == 1 and dumped["user_address"] == "0xabc"
    assert str(dumped["date"]).startswith("2026-11-18")
    assert str(dumped["order_timestamp"]).startswith("2026-11-17")


async def test_levels_carry_snapshot_fields(api):
    body = {"mid_price": 100.0, "snapshot_ts": "2026-11-18T00:00:00Z", "levels": [{"price": 90.0, "long_notional": 5.0}, {"price": 110.0, "short_notional": 7.0}]}
    api([page(body)])
    rows = await g.OxarchiveLiquidationLevelsFetcher.fetch_data({"symbol": "BTC"}, CREDS)
    assert len(rows) == 2 and all(r.model_dump()["mid_price"] == 100.0 for r in rows)


async def test_wallet_routes_by_venue(api):
    calls = api([page({"positions": [{"symbol": "BTC", "size": "1"}]}), page({"positions": [{"symbol": "ETH", "size": "2"}]})])
    await g.OxarchiveWalletPositionsFetcher.fetch_data({"account": "0xabc"}, CREDS)
    await g.OxarchiveWalletPositionsFetcher.fetch_data({"account": "281474976623775", "venue": "lighter"}, CREDS)
    assert calls[0]["url"].endswith("/v1/hyperliquid/wallets/0xabc/positions")
    assert calls[1]["url"].endswith("/v1/lighter/accounts/281474976623775/positions")


async def test_raw_interval_is_not_sent(api):
    calls = api([page([{"symbol": "BTC", "timestamp": "2026-11-18T15:02:05Z", "funding_rate": "0.0000125"}])])
    rows = await g.OxarchiveFundingRatesFetcher.fetch_data({"symbol": "btc", "interval": "raw"}, CREDS)
    assert "interval" not in calls[0]["params"]
    assert rows[0].funding_rate == pytest.approx(0.0000125)


async def test_single_object_routes_do_not_page(api):
    calls = api([page({"symbol": "BTC", "timestamp": "2026-11-18T00:00:00Z", "funding_rate": "0.1"}, cursor="ignored")])
    rows = await g.OxarchiveFundingCurrentFetcher.fetch_data({"symbol": "BTC"}, CREDS)
    assert len(calls) == 1 and len(rows) == 1


def test_unsupported_venue_is_refused():
    with pytest.raises(ValueError):
        g.OxarchiveFundingRatesFetcher.transform_query({"symbol": "HYPE", "venue": "spot"})


async def test_errors(api):
    api([(400, {"success": False, "error": "The symbol 'NOPE' does not exist."})])
    with pytest.raises(OpenBBError, match="NOPE"):
        await g.OxarchiveTradesFetcher.fetch_data({"symbol": "NOPE"}, CREDS)
    api([(403, {"success": False, "error": "History before 30 days needs a paid plan."})])
    with pytest.raises(OpenBBError, match="pricing"):
        await g.OxarchiveTradesFetcher.fetch_data({"symbol": "BTC"}, CREDS)


async def test_bad_and_missing_key(api):
    calls = api([(401, {"success": False, "error": "Authentication error"})])
    with pytest.raises(UnauthorizedError):
        await g.OxarchiveTradesFetcher.fetch_data({"symbol": "BTC"}, CREDS)
    with pytest.raises(UnauthorizedError):
        await g.OxarchiveTradesFetcher.fetch_data({"symbol": "BTC"}, {})
    assert len(calls) == 1


async def test_empty(api):
    api([page([])])
    with pytest.raises(EmptyDataError):
        await g.OxarchiveOpenInterestFetcher.fetch_data({"symbol": "BTC"}, CREDS)


async def test_search_filters(api):
    api([(200, {"success": True, "symbols": [{"symbol": "BTC", "exchange": "hyperliquid"}, {"symbol": "xyz:NVDA", "exchange": "hip3", "display_title": "NVIDIA"}]})])
    rows = await OxarchiveCryptoSearchFetcher.fetch_data({"query": "nvidia"}, CREDS)
    assert [r.symbol for r in rows] == ["xyz:NVDA"]


async def test_candles_default_to_a_chartable_range(api):
    calls = api([page([CANDLE])])
    await OxarchiveCryptoHistoricalFetcher.fetch_data({"symbol": "BTC"}, CREDS)
    start = datetime.fromisoformat(calls[0]["params"]["start"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - start
    assert 28 < age.days <= 29  # inside Free's 30-day window
    calls = api([page([CANDLE])])
    await OxarchiveCryptoHistoricalFetcher.fetch_data({"symbol": "BTC", "interval": "5m"}, CREDS)
    start = datetime.fromisoformat(calls[0]["params"]["start"].replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - start).days == 3


async def test_rate_limit_is_retried(api, monkeypatch):
    async def no_wait(_):
        return None

    monkeypatch.setattr("asyncio.sleep", no_wait)
    calls = api([(429, {"success": False, "error": "Rate limit exceeded"}), page([{"symbol": "BTC", "timestamp": "2026-11-18T00:00:00Z"}])])
    rows = await g.OxarchiveTradesFetcher.fetch_data({"symbol": "BTC"}, CREDS)
    assert len(calls) == 2 and len(rows) == 1


async def test_repeated_cursor_stops_paging(api):
    calls = api([page([{"symbol": "BTC", "timestamp": "2026-11-18T00:00:00Z"}], cursor="same")] * 5)
    await g.OxarchiveTradesFetcher.fetch_data({"symbol": "BTC", "limit": 100}, CREDS)
    assert len(calls) == 2
