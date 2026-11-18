"""Live smoke checks against the real API. Run with: OXARCHIVE_API_KEY=... pytest -m live

codegen/live_sweep.py calls every command on every venue; this file is the quick subset.
"""

import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("OXARCHIVE_API_KEY"), reason="needs OXARCHIVE_API_KEY"),
]


@pytest.fixture(scope="module")
def obb():
    from openbb import obb as app

    app.user.credentials.oxarchive_api_key = os.environ["OXARCHIVE_API_KEY"]
    return app


@pytest.mark.parametrize("symbol,venue", [("BTC", "hyperliquid"), ("ETH", "lighter"), ("xyz:NVDA", "hip3"), ("HYPE", "spot")])
def test_candles(obb, symbol, venue):
    frame = obb.crypto.price.historical(symbol, provider="oxarchive", venue=venue, interval="1h").to_df()
    assert len(frame) > 0 and (frame["high"] >= frame["low"]).all()


def test_order_book_levels(obb):
    frame = obb.oxarchive.orderbook.snapshot(symbol="BTC").to_df()
    assert set(frame["side"]) == {"bid", "ask"} and frame["level"].min() == 1


def test_l4_orders(obb):
    frame = obb.oxarchive.orderbook.l4(symbol="BTC").to_df()
    assert len(frame) > 100 and "user_address" in frame.columns


def test_funding_and_liquidations(obb):
    assert len(obb.oxarchive.market.funding_rates(symbol="BTC").to_df()) > 0
    assert len(obb.oxarchive.liquidations.levels(symbol="BTC").to_df()) > 0


def test_search(obb):
    assert "xyz:NVDA" in set(obb.crypto.search("nvda", provider="oxarchive").to_df()["symbol"])
