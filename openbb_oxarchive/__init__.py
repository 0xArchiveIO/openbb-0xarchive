"""0xArchive provider extension for OpenBB."""

from openbb_core.provider.abstract.provider import Provider

from openbb_oxarchive.models.crypto_historical import OxarchiveCryptoHistoricalFetcher
from openbb_oxarchive.models.generated import FETCHERS
from openbb_oxarchive.models.standard import (
    OxarchiveCryptoSearchFetcher,
    OxarchiveFuturesHistoricalFetcher,
    OxarchiveFuturesInstrumentsFetcher,
)

oxarchive_provider = Provider(
    name="oxarchive",
    website="https://0xarchive.io",
    description="""0xArchive serves historical and live market data for Hyperliquid and
Lighter: order books down to every resting order, trades, candles, funding, open
interest, liquidations, order flow, positions and wallets, across perpetuals, HIP-3
builder markets, HIP-4 outcome markets, Hyperliquid spot and Lighter on Robinhood Chain.""",
    credentials=["api_key"],
    fetcher_dict={
        "CryptoHistorical": OxarchiveCryptoHistoricalFetcher,
        "CryptoSearch": OxarchiveCryptoSearchFetcher,
        "FuturesHistorical": OxarchiveFuturesHistoricalFetcher,
        "FuturesInstruments": OxarchiveFuturesInstrumentsFetcher,
        **FETCHERS,
    },
    repr_name="0xArchive",
    instructions="Create an API key at https://0xarchive.io and set it as `oxarchive_api_key`.",
)
