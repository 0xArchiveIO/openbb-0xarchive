"""0xArchive fetchers for OpenBB standard models: crypto search, futures history and instruments."""

from typing import Any, Literal

from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.crypto_search import (
    CryptoSearchData,
    CryptoSearchQueryParams,
)
from openbb_core.provider.standard_models.futures_historical import (
    FuturesHistoricalData,
    FuturesHistoricalQueryParams,
)
from openbb_core.provider.standard_models.futures_instruments import (
    FuturesInstrumentsData,
    FuturesInstrumentsQueryParams,
)
from openbb_core.provider.utils.errors import EmptyDataError, UnauthorizedError
from pydantic import Field, field_validator

from openbb_oxarchive.utils.engine import _read, run
from openbb_oxarchive.utils.helpers import BASE_URL, CandleInterval, normalize_symbol

PerpVenue = Literal["hyperliquid", "lighter", "hip3", "rh-lighter"]
PERP_HELP = (
    "Where the perpetual trades: hyperliquid, lighter, hip3 (Hyperliquid builder-deployed"
    " perps) or rh-lighter (Lighter on Robinhood Chain)."
)


class OxarchiveCryptoSearchQueryParams(CryptoSearchQueryParams):
    """0xArchive Crypto Search Query. Matches symbol, name or venue."""


class OxarchiveCryptoSearchData(CryptoSearchData):
    """0xArchive Crypto Search Data."""

    exchange: str | None = Field(default=None, description="The venue.")
    coverage_from: str | None = Field(default=None, description="First date with data.")
    coverage_to: str | None = Field(default=None, description="Last date with data.")
    data_types: list | None = Field(default=None, description="Datasets available for the market.")


class OxarchiveCryptoSearchFetcher(
    Fetcher[OxarchiveCryptoSearchQueryParams, list[OxarchiveCryptoSearchData]]
):
    """Search every market 0xArchive covers."""

    require_credentials = True

    @staticmethod
    def transform_query(params: dict[str, Any]) -> OxarchiveCryptoSearchQueryParams:
        return OxarchiveCryptoSearchQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: OxarchiveCryptoSearchQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> list[dict]:
        from openbb_core.provider.utils.helpers import amake_request

        api_key = (credentials or {}).get("oxarchive_api_key")
        if not api_key:
            raise UnauthorizedError("An 0xArchive API key is required. Set it as `oxarchive_api_key`.")
        body = await amake_request(
            f"{BASE_URL}/v1/symbols",
            headers={"X-API-Key": api_key},
            response_callback=_read,
            timeout=60,
            allow_redirects=False,
        )
        rows = body.get("symbols") or (body.get("data") or {}).get("symbols") or []
        needle = (query.query or "").lower()
        hits = [
            row
            for row in rows
            if not needle
            or any(needle in str(row.get(k) or "").lower() for k in ("symbol", "display_title", "exchange", "slug"))
        ]
        if not hits:
            raise EmptyDataError(f"No 0xArchive market matches '{query.query}'.")
        return hits

    @staticmethod
    def transform_data(
        query: OxarchiveCryptoSearchQueryParams, data: list[dict], **kwargs: Any
    ) -> list[OxarchiveCryptoSearchData]:
        return [
            OxarchiveCryptoSearchData.model_validate(
                {
                    "symbol": row.get("symbol"),
                    "name": row.get("display_title") or row.get("symbol"),
                    "exchange": row.get("exchange"),
                    "coverage_from": row.get("coverage_from"),
                    "coverage_to": row.get("coverage_to"),
                    "data_types": row.get("data_types"),
                }
            )
            for row in data
        ]


class OxarchiveFuturesHistoricalQueryParams(FuturesHistoricalQueryParams):
    """0xArchive perpetual futures candles."""

    venue: PerpVenue = Field(default="hyperliquid", description=PERP_HELP)
    interval: CandleInterval = Field(default="1d", description="The candle interval.")
    limit: int = Field(default=10000, ge=1, le=1000000, description="The most candles to return.")

    @field_validator("symbol", mode="after")
    @classmethod
    def _to_archive_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class OxarchiveFuturesHistoricalData(FuturesHistoricalData):
    """0xArchive perpetual futures candles."""

    quote_volume: float | None = Field(default=None, description="Traded volume in the quote currency.")
    trade_count: int | None = Field(default=None, description="Number of trades in the candle.")


class OxarchiveFuturesHistoricalFetcher(
    Fetcher[OxarchiveFuturesHistoricalQueryParams, list[OxarchiveFuturesHistoricalData]]
):
    """Perpetual futures candles. Perpetuals have no expiration, so it is ignored."""

    require_credentials = True

    @staticmethod
    def transform_query(params: dict[str, Any]) -> OxarchiveFuturesHistoricalQueryParams:
        return OxarchiveFuturesHistoricalQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: OxarchiveFuturesHistoricalQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> list[dict]:
        return await run("candles", query, credentials, page_max=10000)

    @staticmethod
    def transform_data(
        query: OxarchiveFuturesHistoricalQueryParams, data: list[dict], **kwargs: Any
    ) -> list[OxarchiveFuturesHistoricalData]:
        return [OxarchiveFuturesHistoricalData.model_validate(row) for row in data]


class OxarchiveFuturesInstrumentsQueryParams(FuturesInstrumentsQueryParams):
    """0xArchive perpetual futures listings."""

    venue: PerpVenue = Field(default="hyperliquid", description=PERP_HELP)


class OxarchiveFuturesInstrumentsData(FuturesInstrumentsData):
    """0xArchive perpetual futures listing."""

    symbol: str | None = Field(default=None, description="The market.")
    max_leverage: float | None = Field(default=None, description="Maximum leverage.")
    sz_decimals: int | None = Field(default=None, description="Size decimals.")
    is_active: bool | None = Field(default=None, description="Whether the market is trading.")


class OxarchiveFuturesInstrumentsFetcher(
    Fetcher[OxarchiveFuturesInstrumentsQueryParams, list[OxarchiveFuturesInstrumentsData]]
):
    """Perpetual futures listed on a venue."""

    require_credentials = True

    @staticmethod
    def transform_query(params: dict[str, Any]) -> OxarchiveFuturesInstrumentsQueryParams:
        return OxarchiveFuturesInstrumentsQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: OxarchiveFuturesInstrumentsQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> list[dict]:
        return await run("instruments", query, credentials)

    @staticmethod
    def transform_data(
        query: OxarchiveFuturesInstrumentsQueryParams, data: list[dict], **kwargs: Any
    ) -> list[OxarchiveFuturesInstrumentsData]:
        out = []
        for row in data:
            row = dict(row)
            row.setdefault("symbol", row.get("name"))
            out.append(OxarchiveFuturesInstrumentsData.model_validate(row))
        return out
