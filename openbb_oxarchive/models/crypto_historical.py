"""0xArchive Crypto Historical Price Model."""

from typing import Any

from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.crypto_historical import (
    CryptoHistoricalData,
    CryptoHistoricalQueryParams,
)
from pydantic import Field, field_validator

from openbb_oxarchive.utils.engine import run
from openbb_oxarchive.utils.helpers import CandleInterval, Venue, normalize_symbol


class OxarchiveCryptoHistoricalQueryParams(CryptoHistoricalQueryParams):
    """0xArchive Crypto Historical Price Query.

    Source: https://docs.0xarchive.io
    """

    venue: Venue = Field(
        default="hyperliquid",
        description="Where the market trades: hyperliquid (perps), lighter, hip3"
        + " (Hyperliquid builder-deployed perps such as xyz:NVDA), hip4 (Hyperliquid"
        + " outcome markets), spot (Hyperliquid spot) or rh-lighter (Lighter on"
        + " Robinhood Chain).",
    )
    interval: CandleInterval = Field(default="1d", description="The candle interval.")
    limit: int = Field(
        default=10000, ge=1, le=100000, description="The most candles to return."
    )

    @field_validator("symbol", mode="after")
    @classmethod
    def _to_archive_symbol(cls, value: str) -> str:
        """Use the 0xArchive symbol form."""
        return normalize_symbol(value)


class OxarchiveCryptoHistoricalData(CryptoHistoricalData):
    """0xArchive Crypto Historical Price Data."""

    quote_volume: float | None = Field(
        default=None, description="Traded volume in the quote currency."
    )
    trade_count: int | None = Field(
        default=None, description="Number of trades in the candle."
    )


class OxarchiveCryptoHistoricalFetcher(
    Fetcher[OxarchiveCryptoHistoricalQueryParams, list[OxarchiveCryptoHistoricalData]]
):
    """Fetch OHLCV candles from 0xArchive."""

    require_credentials = True

    @staticmethod
    def transform_query(params: dict[str, Any]) -> OxarchiveCryptoHistoricalQueryParams:
        """Validate the query."""
        return OxarchiveCryptoHistoricalQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: OxarchiveCryptoHistoricalQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> list[dict]:
        """Read every candle in the range."""
        return await run("candles", query, credentials, page_max=10000)

    @staticmethod
    def transform_data(
        query: OxarchiveCryptoHistoricalQueryParams, data: list[dict], **kwargs: Any
    ) -> list[OxarchiveCryptoHistoricalData]:
        """Type each candle."""
        return [OxarchiveCryptoHistoricalData.model_validate(row) for row in data]
