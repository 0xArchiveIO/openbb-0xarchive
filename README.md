# openbb-0xarchive

Hyperliquid and Lighter market data from [0xArchive](https://0xarchive.io) inside the [OpenBB Platform](https://openbb.co) and OpenBB Workspace.

Order books down to every resting order, trades, candles, funding, open interest, liquidations, order flow, positions and wallets. Venues: Hyperliquid perps, HIP-3 builder markets, HIP-4 outcome markets, Hyperliquid spot, Lighter, and Lighter on Robinhood Chain.

## Install

```bash
pip install openbb openbb-0xarchive
```

Add `openbb-derivatives` to also list 0xArchive perps under `obb.derivatives.futures`.

## API key

Create a key at [0xarchive.io](https://0xarchive.io), then set it once:

```python
from openbb import obb

obb.user.credentials.oxarchive_api_key = "YOUR_KEY"
```

Or add `"oxarchive_api_key": "YOUR_KEY"` to `credentials` in `~/.openbb_platform/user_settings.json`.

Sample data: one free week of Hyperliquid and Lighter data, as Parquet, on [Hugging Face](https://huggingface.co/datasets/0xArchive/hyperliquid-lighter-market-data-sample).

## Use

```python
from datetime import date, datetime, timedelta, timezone

from openbb import obb

week_ago = date.today() - timedelta(days=7)
hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

# Find a market
obb.crypto.search("nvda", provider="oxarchive").to_df()

# Candles, through OpenBB's standard crypto command
obb.crypto.price.historical("BTC", provider="oxarchive").to_df()
obb.crypto.price.historical("xyz:NVDA", provider="oxarchive", venue="hip3", interval="1h", start_date=week_ago)

# Order books: one row per price level, or per resting order for L4
obb.oxarchive.orderbook.snapshot(symbol="ETH", venue="lighter").to_df()
obb.oxarchive.orderbook.history(symbol="BTC", start_date=hour_ago, depth=20)
obb.oxarchive.orderbook.l4(symbol="BTC")
obb.oxarchive.orderbook.l4_diffs(symbol="BTC", start_date=hour_ago)  # order-by-order changes

# Liquidations and positioning
obb.oxarchive.liquidations.levels(symbol="BTC")
obb.oxarchive.liquidations.volume(symbol="SOL", venue="lighter", interval="1d", start_date=week_ago)

# Funding, open interest and trades
obb.oxarchive.market.funding_rates(symbol="BTC", start_date=week_ago)
obb.oxarchive.market.trades(symbol="HYPE", venue="spot", side="buy", start_date=hour_ago, limit=5000)

# A wallet
obb.oxarchive.wallets.positions(account="0x...")
```

Every command takes `venue` where more than one applies. Symbols use the 0xArchive form: `BTC`, `xyz:NVDA`, `HYPE`, and `#<id>` for HIP-4 outcomes. `BTC-USD` and `BTC-PERP` are accepted and mapped to `BTC`.

History commands return rows oldest first, from `start_date` to `end_date`, and page through the API for you. Without dates they cover the last 24 hours; candles cover the last 29 days, or less for minute intervals. `limit` caps the rows returned (snapshots, for order book history). For the latest trades, pass a recent `start_date`, or use `market.trades_recent` on venues that offer it. Funding, open interest, prices and similar series default to hourly; pass `interval="raw"` for every update.

History depth and dataset access depend on your plan. A request outside your plan returns the reason and a link to [pricing](https://0xarchive.io/pricing). Full field documentation is in the [API docs](https://docs.0xarchive.io).

## OpenBB Workspace

Every command is also a Workspace widget under **Crypto**, grouped as below. Run `openbb-api` and add the backend in Workspace.

## Commands

Also through OpenBB's standard commands: `obb.crypto.price.historical`, `obb.crypto.search`, and with `openbb-derivatives`, `obb.derivatives.futures.historical` and `obb.derivatives.futures.instruments`.

### Market data

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.market.trades` | Trades | HL, Lighter, HIP-3, HIP-4, Spot, Lighter (Robinhood) |
| `obb.oxarchive.market.trades_recent` | Most recent trades | Lighter, HIP-3, HIP-4, Spot, Lighter (Robinhood) |
| `obb.oxarchive.market.candles` | OHLCV candles | HL, Lighter, HIP-3, HIP-4, Spot, Lighter (Robinhood) |
| `obb.oxarchive.market.funding_rates` | Funding rate history | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.market.funding_current` | Current funding rate | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.market.open_interest` | Open interest history | HL, Lighter, HIP-3, Lighter (Robinhood), HIP-4 |
| `obb.oxarchive.market.open_interest_current` | Current open interest | HL, Lighter, HIP-3, Lighter (Robinhood), HIP-4 |
| `obb.oxarchive.market.prices` | Mark, oracle and mid price history | HL, Lighter, HIP-3, Lighter (Robinhood), HIP-4 |
| `obb.oxarchive.market.summary` | Market summary: price, funding, open interest, volume and liquidations | HL, Lighter, HIP-3, Lighter (Robinhood), HIP-4 |

### Order books

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.orderbook.snapshot` | Order book snapshot, one row per price level | HL, Lighter, HIP-3, HIP-4, Spot, Lighter (Robinhood) |
| `obb.oxarchive.orderbook.history` | Order book history, one row per price level per snapshot | HL, Lighter, HIP-3, HIP-4, Spot, Lighter (Robinhood) |
| `obb.oxarchive.orderbook.l2` | Full-depth L2 order book snapshot | HL, HIP-3 |
| `obb.oxarchive.orderbook.l2_history` | Full-depth L2 order book history | HL, HIP-3 |
| `obb.oxarchive.orderbook.l2_diffs` | Full-depth L2 order book changes | HL, HIP-3 |
| `obb.oxarchive.orderbook.l4` | L4 order book: every resting order with its wallet | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.orderbook.l4_history` | L4 order book history | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.orderbook.l4_diffs` | L4 order book changes, order by order | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.orderbook.l3` | Lighter L3 order book: every resting order with its account | Lighter |
| `obb.oxarchive.orderbook.l3_history` | Lighter L3 order book history | Lighter |

### Liquidations

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.liquidations.events` | Liquidation events | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.liquidations.volume` | Liquidation volume by interval, long and short | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.liquidations.levels` | Projected forced-liquidation price levels | HL, HIP-3 |
| `obb.oxarchive.liquidations.levels_history` | Projected forced-liquidation price level history | HL, HIP-3 |
| `obb.oxarchive.liquidations.by_wallet` | Liquidations of one wallet | HL |

### Order flow

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.flow.cvd` | Cumulative volume delta | HL, HIP-3 |
| `obb.oxarchive.flow.order_flow` | Order placement, cancel and fill flow by interval | HL, HIP-3, HIP-4 |
| `obb.oxarchive.flow.orders` | Order history: placements, cancels, fills and triggers | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.flow.tpsl` | Take-profit and stop-loss orders | HL, HIP-3, HIP-4 |
| `obb.oxarchive.flow.trigger_levels` | Resting trigger orders by price level | HL, HIP-3 |
| `obb.oxarchive.flow.trigger_levels_history` | Resting trigger order level history | HL, HIP-3 |
| `obb.oxarchive.flow.twap` | TWAP orders on a market | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.flow.twap_by_wallet` | TWAP orders of one wallet | HL, HIP-3, HIP-4, Spot |
| `obb.oxarchive.flow.trade_intent` | Fill volume by intent: opens, take-profits, stops, flips | HL, HIP-3 |
| `obb.oxarchive.flow.positioning` | Positioning by market: open interest and taker flow over a window | HL, HIP-3 |

### Market breadth

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.breadth.above_vwap` | Share of markets above session VWAP, history | HL, HIP-3 |
| `obb.oxarchive.breadth.above_vwap_current` | Share of markets above session VWAP, now | HL, HIP-3 |
| `obb.oxarchive.breadth.above_ma` | Share of markets above a moving average, history | HL, HIP-3 |
| `obb.oxarchive.breadth.above_ma_current` | Share of markets above a moving average, now | HL, HIP-3 |

### Positions

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.positions.market` | Every open position on a market | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.positions.long_short` | Long and short position totals on a market, history | HL, Lighter, HIP-3, Lighter (Robinhood) |
| `obb.oxarchive.positions.all` | Every open position on every market | HL, Lighter, HIP-3, Lighter (Robinhood) |

### Wallets and accounts

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.wallets.profile` | Trading profile of a wallet | HL, HIP-3 |
| `obb.oxarchive.wallets.screen` | Screen wallets by trading behaviour | HL, HIP-3 |
| `obb.oxarchive.wallets.positions` | Open positions of a wallet or account | HL, HIP-3, Lighter, Lighter (Robinhood) |
| `obb.oxarchive.wallets.positions_history` | Position history of a wallet or account | HL, HIP-3, Lighter, Lighter (Robinhood) |
| `obb.oxarchive.wallets.position_changes` | Position changes of a wallet or account | HL, HIP-3, Lighter, Lighter (Robinhood) |
| `obb.oxarchive.wallets.account` | Account value and margin of a wallet or account | HL, HIP-3, Lighter, Lighter (Robinhood) |
| `obb.oxarchive.wallets.account_history` | Account value and margin history | HL, HIP-3, Lighter, Lighter (Robinhood) |
| `obb.oxarchive.wallets.funding` | Funding paid and received by a wallet | HL, HIP-3 |
| `obb.oxarchive.wallets.lighter_accounts` | Lighter accounts owned by an address | Lighter |
| `obb.oxarchive.wallets.usdc_flows` | Hyperliquid USDC deposits, withdrawals and EVM transfers | HL |
| `obb.oxarchive.wallets.usdc_flow_volume` | Hyperliquid USDC flow totals by interval | HL |

### Reference

| Command | What it returns | Venues |
| --- | --- | --- |
| `obb.oxarchive.reference.instruments` | Listed markets with their trading rules | HL, Lighter, HIP-3, Lighter (Robinhood), HIP-4 |
| `obb.oxarchive.reference.spot_pairs` | Hyperliquid spot pairs | Spot |
| `obb.oxarchive.reference.outcomes` | HIP-4 outcome markets | HIP-4 |
| `obb.oxarchive.reference.questions` | HIP-4 questions and their outcomes | HIP-4 |
| `obb.oxarchive.reference.oracle_price` | HIP-3 external oracle price | HIP-3 |
| `obb.oxarchive.reference.discovery_bounds` | HIP-3 price discovery bounds | HIP-3 |

## Develop

Commands are defined as data in `openbb_oxarchive/registry.py`. `codegen/generate.py` writes the models and router from that table, the OpenAPI spec and live samples.

```bash
uv sync --locked --group live                 # installs exactly what uv.lock pins, hash-checked
uv run pytest                                 # offline tests
OXARCHIVE_API_KEY=... uv run pytest -m live   # quick live checks
OXARCHIVE_API_KEY=... uv run codegen/generate.py --refresh-spec   # regenerate after an API change
OXARCHIVE_API_KEY=... uv run codegen/live_sweep.py                # every command on every venue
```

## Security

Report a vulnerability privately through this repository's Security tab (Report a vulnerability) or 0xArchive support, not in a public issue. Releases are built and published from GitHub Actions through PyPI Trusted Publishing, with every action pinned to a commit and the build backend pinned by hash.

## License

MIT
