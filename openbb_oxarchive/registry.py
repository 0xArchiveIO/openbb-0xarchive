"""Every 0xArchive dataset the extension exposes, as data.

``codegen/generate.py`` reads this table, the OpenAPI spec and one live sample
per command, then writes ``models/generated.py`` and ``oxarchive_router.py``.
The runtime engine reads it to build each request.

Keys per command:
- ``group`` / ``name``: the OpenBB path, ``obb.oxarchive.<group>.<name>``.
- ``venues``: venue -> route suffix appended to the venue prefix.
- ``args``: path arguments, in order of appearance in the route.
- ``rows``: key inside ``data`` holding the list of rows, if not ``data`` itself.
- ``explode``: nested list turned into one row per item. A list of keys
  (``["bids", "asks"]``) also adds a ``side`` column.
- ``single``: the route returns one object instead of a list.
- ``defaults``: query defaults that differ from the API's.
- ``limit``: (default, maximum) for ``limit`` where full-depth snapshots make
  large values impractical: one Hyperliquid BTC L4 snapshot is ~55,000 rows.
"""

PERPS = ("hyperliquid", "lighter", "hip3", "rh-lighter")
ALL = ("hyperliquid", "lighter", "hip3", "hip4", "spot", "rh-lighter")


def same(venues, suffix):
    """Map each venue to one suffix."""
    return {venue: suffix for venue in venues}


def wallet(suffix):
    """Hyperliquid wallets by address, Lighter accounts by index."""
    return {
        "hyperliquid": f"/wallets/{{account}}{suffix}",
        "hip3": f"/wallets/{{account}}{suffix}",
        "lighter": f"/accounts/{{account}}{suffix}",
        "rh-lighter": f"/accounts/{{account}}{suffix}",
    }


COMMANDS: dict[str, dict] = {
    # Market data
    "trades": dict(group="market", name="trades", title="Trades", venues=same(ALL, "/trades/{symbol}"), args=["symbol"]),
    "trades_recent": dict(group="market", name="trades_recent", title="Most recent trades", venues=same(("lighter", "hip3", "hip4", "spot", "rh-lighter"), "/trades/{symbol}/recent"), args=["symbol"], paged=False),
    "candles": dict(group="market", name="candles", title="OHLCV candles", venues=same(ALL, "/candles/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "funding_rates": dict(group="market", name="funding_rates", title="Funding rate history", venues=same(PERPS, "/funding/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "funding_current": dict(group="market", name="funding_current", title="Current funding rate", venues=same(PERPS, "/funding/{symbol}/current"), args=["symbol"], single=True),
    "open_interest": dict(group="market", name="open_interest", title="Open interest history", venues=same(PERPS + ("hip4",), "/openinterest/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "open_interest_current": dict(group="market", name="open_interest_current", title="Current open interest", venues=same(PERPS + ("hip4",), "/openinterest/{symbol}/current"), args=["symbol"], single=True),
    "prices": dict(group="market", name="prices", title="Mark, oracle and mid price history", venues=same(PERPS + ("hip4",), "/prices/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "summary": dict(group="market", name="summary", title="Market summary: price, funding, open interest, volume and liquidations", venues=same(PERPS + ("hip4",), "/summary/{symbol}"), args=["symbol"], single=True),
    # Order books
    "book": dict(group="orderbook", name="snapshot", title="Order book snapshot, one row per price level", venues=same(ALL, "/orderbook/{symbol}"), args=["symbol"], single=True, explode=["bids", "asks"]),
    "book_history": dict(group="orderbook", name="history", title="Order book history, one row per price level per snapshot", venues=same(ALL, "/orderbook/{symbol}/history"), args=["symbol"], explode=["bids", "asks"], defaults={"depth": 10}),
    "book_l2": dict(group="orderbook", name="l2", title="Full-depth L2 order book snapshot", venues=same(("hyperliquid", "hip3"), "/orderbook/{symbol}/l2"), args=["symbol"], single=True, explode=["bids", "asks"], defaults={"depth": 100}),
    "book_l2_history": dict(group="orderbook", name="l2_history", title="Full-depth L2 order book history", venues=same(("hyperliquid", "hip3"), "/orderbook/{symbol}/l2/history"), args=["symbol"], explode=["bids", "asks"], defaults={"depth": 100}, limit=(100, 5000)),
    "book_l2_diffs": dict(group="orderbook", name="l2_diffs", title="Full-depth L2 order book changes", venues=same(("hyperliquid", "hip3"), "/orderbook/{symbol}/l2/diffs"), args=["symbol"]),
    "book_l4": dict(group="orderbook", name="l4", title="L4 order book: every resting order with its wallet", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/orderbook/{symbol}/l4"), args=["symbol"], single=True, explode=["bids", "asks"]),
    "book_l4_history": dict(group="orderbook", name="l4_history", title="L4 order book history", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/orderbook/{symbol}/l4/history"), args=["symbol"], explode=["bids", "asks"], limit=(1, 10)),
    "book_l4_diffs": dict(group="orderbook", name="l4_diffs", title="L4 order book changes, order by order", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/orderbook/{symbol}/l4/diffs"), args=["symbol"]),
    "book_l3": dict(group="orderbook", name="l3", title="Lighter L3 order book: every resting order with its account", venues={"lighter": "/l3orderbook/{symbol}"}, args=["symbol"], single=True, explode=["orders"]),
    "book_l3_history": dict(group="orderbook", name="l3_history", title="Lighter L3 order book history", venues={"lighter": "/l3orderbook/{symbol}/history"}, args=["symbol"], explode=["orders"], limit=(20, 200)),
    # Liquidations
    "liquidations": dict(group="liquidations", name="events", title="Liquidation events", venues=same(PERPS, "/liquidations/{symbol}"), args=["symbol"]),
    "liquidation_volume": dict(group="liquidations", name="volume", title="Liquidation volume by interval, long and short", venues=same(PERPS, "/liquidations/{symbol}/volume"), args=["symbol"], defaults={"interval": "1h"}),
    "liquidation_levels": dict(group="liquidations", name="levels", title="Projected forced-liquidation price levels", venues=same(("hyperliquid", "hip3"), "/liquidations/{symbol}/levels"), args=["symbol"], single=True, explode=["levels"]),
    "liquidation_levels_history": dict(group="liquidations", name="levels_history", title="Projected forced-liquidation price level history", venues=same(("hyperliquid", "hip3"), "/liquidations/{symbol}/levels/history"), args=["symbol"], explode=["levels"]),
    "liquidations_by_user": dict(group="liquidations", name="by_wallet", title="Liquidations of one wallet", venues={"hyperliquid": "/liquidations/user/{user}"}, args=["user"]),
    # Order flow
    "cvd": dict(group="flow", name="cvd", title="Cumulative volume delta", venues=same(("hyperliquid", "hip3"), "/cvd/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "order_flow": dict(group="flow", name="order_flow", title="Order placement, cancel and fill flow by interval", venues=same(("hyperliquid", "hip3", "hip4"), "/orders/{symbol}/flow"), args=["symbol"]),
    "orders": dict(group="flow", name="orders", title="Order history: placements, cancels, fills and triggers", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/orders/{symbol}/history"), args=["symbol"]),
    "tpsl": dict(group="flow", name="tpsl", title="Take-profit and stop-loss orders", venues=same(("hyperliquid", "hip3", "hip4"), "/orders/{symbol}/tpsl"), args=["symbol"]),
    "trigger_levels": dict(group="flow", name="trigger_levels", title="Resting trigger orders by price level", venues=same(("hyperliquid", "hip3"), "/orders/{symbol}/trigger-levels"), args=["symbol"], single=True, explode=["levels"]),
    "trigger_levels_history": dict(group="flow", name="trigger_levels_history", title="Resting trigger order level history", venues=same(("hyperliquid", "hip3"), "/orders/{symbol}/trigger-levels/history"), args=["symbol"], explode=["levels"]),
    "twap": dict(group="flow", name="twap", title="TWAP orders on a market", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/twap/{symbol}"), args=["symbol"]),
    "twap_by_user": dict(group="flow", name="twap_by_wallet", title="TWAP orders of one wallet", venues=same(("hyperliquid", "hip3", "hip4", "spot"), "/twap/user/{user}"), args=["user"]),
    "trade_intent": dict(group="flow", name="trade_intent", title="Fill volume by intent: opens, take-profits, stops, flips", venues=same(("hyperliquid", "hip3"), "/trade-intent/{symbol}"), args=["symbol"], defaults={"interval": "1h"}),
    "positioning": dict(group="flow", name="positioning", title="Positioning by market: open interest and taker flow over a window", venues=same(("hyperliquid", "hip3"), "/positioning"), args=[], paged=False, defaults={"window": "24h"}),
    # Breadth
    "breadth_vwap": dict(group="breadth", name="above_vwap", title="Share of markets above session VWAP, history", venues=same(("hyperliquid", "hip3"), "/breadth/above-vwap"), args=[], defaults={"interval": "1h"}),
    "breadth_vwap_current": dict(group="breadth", name="above_vwap_current", title="Share of markets above session VWAP, now", venues=same(("hyperliquid", "hip3"), "/breadth/above-vwap/current"), args=[], single=True),
    "breadth_ma": dict(group="breadth", name="above_ma", title="Share of markets above a moving average, history", venues=same(("hyperliquid", "hip3"), "/breadth/above-ma"), args=[], defaults={"interval": "1h", "n": 20}),
    "breadth_ma_current": dict(group="breadth", name="above_ma_current", title="Share of markets above a moving average, now", venues=same(("hyperliquid", "hip3"), "/breadth/above-ma/current"), args=[], single=True, defaults={"n": 20}),
    # Positions across all traders
    "positions": dict(group="positions", name="market", title="Every open position on a market", venues=same(PERPS, "/positions/{symbol}"), args=["symbol"]),
    "positions_summary": dict(group="positions", name="long_short", title="Long and short position totals on a market, history", venues=same(PERPS, "/positions/{symbol}/summary"), args=["symbol"]),
    "positions_all": dict(group="positions", name="all", title="Every open position on every market", venues=same(PERPS, "/positions"), args=[], hidden=("format",)),
    # Wallets and accounts
    "wallet_profile": dict(group="wallets", name="profile", title="Trading profile of a wallet", venues=same(("hyperliquid", "hip3"), "/wallets/{address}/profile"), args=["address"], single=True),
    "wallet_classify": dict(group="wallets", name="screen", title="Screen wallets by trading behaviour", venues=same(("hyperliquid", "hip3"), "/wallets/classify"), args=[], rows="wallets", paged=False),
    "wallet_positions": dict(group="wallets", name="positions", title="Open positions of a wallet or account", venues=wallet("/positions"), args=["account"], rows="positions"),
    "wallet_positions_history": dict(group="wallets", name="positions_history", title="Position history of a wallet or account", venues=wallet("/positions/history"), args=["account"]),
    "wallet_position_changes": dict(group="wallets", name="position_changes", title="Position changes of a wallet or account", venues=wallet("/positions/changes"), args=["account"]),
    "wallet_account": dict(group="wallets", name="account", title="Account value and margin of a wallet or account", venues=wallet("/account"), args=["account"], paged=False),
    "wallet_account_history": dict(group="wallets", name="account_history", title="Account value and margin history", venues=wallet("/account/history"), args=["account"]),
    "wallet_funding": dict(group="wallets", name="funding", title="Funding paid and received by a wallet", venues=same(("hyperliquid", "hip3"), "/wallets/{address}/funding"), args=["address"]),
    "lighter_accounts": dict(group="wallets", name="lighter_accounts", title="Lighter accounts owned by an address", venues=same(("lighter",), "/accounts"), args=[], rows="accounts"),
    "usdc_flows": dict(group="wallets", name="usdc_flows", title="Hyperliquid USDC deposits, withdrawals and EVM transfers", venues={"hyperliquid": "/usdc-flows"}, args=[]),
    "usdc_flow_volume": dict(group="wallets", name="usdc_flow_volume", title="Hyperliquid USDC flow totals by interval", venues={"hyperliquid": "/usdc-flows/volume"}, args=[], defaults={"interval": "1h"}),
    # Reference
    "instruments": dict(group="reference", name="instruments", title="Listed markets with their trading rules", venues=same(PERPS + ("hip4",), "/instruments"), args=[], paged=False),
    "spot_pairs": dict(group="reference", name="spot_pairs", title="Hyperliquid spot pairs", venues={"spot": "/pairs"}, args=[], paged=False),
    "outcomes": dict(group="reference", name="outcomes", title="HIP-4 outcome markets", venues={"hip4": "/outcomes"}, args=[]),
    "questions": dict(group="reference", name="questions", title="HIP-4 questions and their outcomes", venues={"hip4": "/questions"}, args=[]),
    "oracle_price": dict(group="reference", name="oracle_price", title="HIP-3 external oracle price", venues={"hip3": "/oracle/external-price/{symbol}"}, args=["symbol"], single=True),
    "discovery_bounds": dict(group="reference", name="discovery_bounds", title="HIP-3 price discovery bounds", venues={"hip3": "/oracle/discovery-bounds/{symbol}"}, args=["symbol"], single=True),
}

ARG_HELP = {
    "symbol": "The market, for example BTC, xyz:NVDA or HYPE.",
    "user": "The wallet address.",
    "address": "The wallet address.",
    "account": "A Hyperliquid wallet address, or a Lighter account index.",
}
