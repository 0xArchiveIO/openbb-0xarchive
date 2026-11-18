"""Generate the models and router from the registry, the OpenAPI spec and live samples.

    OXARCHIVE_API_KEY=... python codegen/generate.py [--refresh-spec]

Writes openbb_oxarchive/models/generated.py and openbb_oxarchive/oxarchive_router.py,
plus codegen/samples.json (field lists seen live, kept so a rerun without a key
reproduces the same code).
"""

import json
import keyword
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Importing the package loads the previous output. Start from a stub so a broken
# earlier run cannot block regeneration.
_GENERATED = ROOT / "openbb_oxarchive" / "models" / "generated.py"
try:
    compile(_GENERATED.read_text(), str(_GENERATED), "exec")
except (OSError, SyntaxError):
    _GENERATED.write_text("FETCHERS: dict = {}\n")

from openbb_oxarchive.registry import ARG_HELP, COMMANDS  # noqa: E402
from openbb_oxarchive.utils.engine import VENUE_PATHS, build_request, shape_rows  # noqa: E402

SPEC_PATH = ROOT / "codegen" / "openapi.json"
SAMPLES_PATH = ROOT / "codegen" / "samples.json"
SKIP_PARAMS = {"cursor", "cursor_seq", "limit", "start", "end", "format"}
TEXT_HINTS = re.compile(
    r"(symbol|coin|side|direction|hash|user|address|kind|dex|status|name|description|source|type|slug|class"
    r"|underlying|period|method|token|cloid|title|expiry|session_date|window|sort|order$|account|quality|id$|tif)",
    re.I,
)
GROUP_TITLES = {
    "market": "Market data",
    "orderbook": "Order books",
    "liquidations": "Liquidations",
    "flow": "Order flow",
    "breadth": "Market breadth",
    "positions": "Positions",
    "wallets": "Wallets and accounts",
    "reference": "Reference",
}


def load_spec(refresh: bool) -> dict:
    if refresh or not SPEC_PATH.exists():
        with urllib.request.urlopen("https://0xarchive.io/openapi.json", timeout=60) as resp:
            SPEC_PATH.write_bytes(resp.read())
    return json.loads(SPEC_PATH.read_text())


def resolve(spec: dict, node: dict) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        node = spec["components"]["schemas"][node["$ref"].split("/")[-1]]
    return node or {}


def operation(spec: dict, key: str, venue: str) -> dict:
    suffix = COMMANDS[key]["venues"][venue]
    template = VENUE_PATHS[venue] + re.sub(r"\{(\w+)\}", "{}", suffix)
    for path, item in spec["paths"].items():
        if re.sub(r"\{\w+\}", "{}", path) == template and "get" in item:
            return item["get"]
    raise KeyError(f"{key}: no OpenAPI route for {venue} {suffix}")


def descriptions(spec: dict, node: dict, out: dict, depth: int = 0) -> dict:
    """Collect property descriptions from a response schema, nested ones included."""
    node = resolve(spec, node)
    if depth > 6:
        return out
    for name, prop in (node.get("properties") or {}).items():
        prop = resolve(spec, prop)
        if prop.get("description") and name not in out:
            out[name] = prop["description"].split("\n")[0].strip()
        descriptions(spec, prop, out, depth + 1)
    if node.get("type") == "array":
        descriptions(spec, node.get("items") or {}, out, depth + 1)
    for combo in ("allOf", "oneOf", "anyOf"):
        for part in node.get(combo, []):
            descriptions(spec, part, out, depth + 1)
    return out


def spec_fields(spec: dict, op: dict) -> dict:
    schema = resolve(spec, op["responses"]["200"]["content"]["application/json"]["schema"])
    data = schema.get("properties", {}).get("data", schema)
    return descriptions(spec, data, {})


# ---------------------------------------------------------------- live samples


def http(path: str, params: dict, key: str) -> dict | None:
    query = "&".join(f"{k}={urllib.request.quote(str(v), safe='')}" for k, v in params.items())
    req = urllib.request.Request(f"{path}?{query}", headers={"X-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        print(f"   HTTP {err.code}: {err.read()[:160]!r}")
        return None


def sample_args(api_key: str) -> dict:
    """Pick live identifiers to sample with."""
    base = "https://api.0xarchive.io"
    hl = http(f"{base}/v1/hyperliquid/trades/BTC", {"limit": 5}, api_key)["data"]
    lt = http(f"{base}/v1/lighter/trades/BTC", {"limit": 5}, api_key)["data"]
    rh = http(f"{base}/v1/rh-lighter/trades/BTC", {"limit": 5}, api_key)["data"]
    symbols = http(f"{base}/v1/symbols", {}, api_key)["symbols"]
    hip4 = max((x for x in symbols if x["exchange"] == "hip4"), key=lambda x: x.get("coverage_to") or "")
    twap = http(f"{base}/v1/hyperliquid/twap/BTC", {"limit": 20}, api_key)["data"]
    lighter_owner = http(f"{base}/v1/lighter/accounts", {"l1_address": "0x0000000000000000000000000000000000000000", "limit": 1}, api_key)
    return {
        "symbol": {"hyperliquid": "BTC", "lighter": "BTC", "rh-lighter": "BTC", "hip3": "xyz:NVDA", "spot": "HYPE", "hip4": hip4["symbol"]},
        "user": next((t["user_address"] for t in twap if t.get("user_address")), None),
        "address": next(t["user_address"] for t in hl if t.get("user_address")),
        "account": {
            "hyperliquid": next(t["user_address"] for t in hl if t.get("user_address")),
            "hip3": next(t["user_address"] for t in hl if t.get("user_address")),
            "lighter": lt[0]["account_index"],
            "rh-lighter": rh[0].get("account_index"),
        },
    }


class Query(dict):
    """A plain query standing in for the validated model while sampling."""

    def model_dump(self):
        return dict(self)


def collect_samples(spec: dict, api_key: str, only: set | None = None) -> dict:
    ids = sample_args(api_key)
    samples: dict = json.loads(SAMPLES_PATH.read_text()) if only and SAMPLES_PATH.exists() else {}
    for key, cfg in COMMANDS.items():
        if only and key not in only:
            continue
        fields: dict = {}
        for venue in cfg["venues"]:
            values: dict = dict(cfg.get("defaults", {}))
            for arg in cfg["args"]:
                pick = ids["symbol"] if arg == "symbol" else ids["account"] if arg == "account" else ids["user"] if arg == "user" and key.startswith("twap") else ids["address"]
                values[arg] = pick[venue] if isinstance(pick, dict) else pick
            if key == "lighter_accounts":
                continue
            values["limit"] = 50
            if key == "positioning":
                values["window"] = "24h"
            url, params = build_request(key, Query(values), venue)
            params["limit"] = 50 if cfg.get("paged", True) and not cfg.get("single") else params.get("limit")
            params = {k: v for k, v in params.items() if v is not None}
            if cfg.get("single") or key in {"instruments", "spot_pairs", "positioning", "wallet_account"}:
                params.pop("limit", None)
            print(f"{key} [{venue}] {url}")
            body = http(url, params, api_key)
            if not body:
                continue
            for row in shape_rows(key, body.get("data"))[:300]:
                for name, value in row.items():
                    if value is not None:
                        fields.setdefault(name, []).append(value)
        if fields or key not in samples:
            samples[key] = {name: kind_of(values) for name, values in fields.items()}
    return samples


def kind_of(values: list) -> str:
    kinds = set()
    for value in values[:200]:
        if isinstance(value, bool):
            kinds.add("bool")
        elif isinstance(value, int):
            kinds.add("int")
        elif isinstance(value, float):
            kinds.add("float")
        elif isinstance(value, (list, dict)):
            kinds.add("list")
        elif isinstance(value, datetime):
            kinds.add("datetime")
        elif isinstance(value, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:?\d{2})?", value):
                kinds.add("datetime")
            elif re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", value):
                kinds.add("numstr")
            else:
                kinds.add("str")
    if kinds <= {"int"}:
        return "int"
    if kinds <= {"int", "float"}:
        return "float"
    if kinds <= {"numstr", "int", "float"}:
        return "numstr"
    if kinds == {"datetime"}:
        return "datetime"
    if kinds == {"bool"}:
        return "bool"
    if kinds == {"list"}:
        return "list"
    return "str"


# ---------------------------------------------------------------- code writing


def camel(key: str) -> str:
    return "Oxarchive" + "".join(part.capitalize() for part in key.split("_"))


def py_type(kind: str, name: str) -> str:
    if kind in ("int", "datetime") and re.search(r"(timestamp|_ts|_at|_time)$", name):
        return "datetime | None"
    if kind == "numstr":
        return "str | None" if TEXT_HINTS.search(name) else "float | None"
    return {"int": "int | None", "float": "float | None", "bool": "bool | None", "datetime": "datetime | None", "list": "list | None"}.get(kind, "str | None")


def human(name: str) -> str:
    return name.replace("_", " ").capitalize() + "."


def lit(values) -> str:
    return "Literal[" + ", ".join(repr(v) for v in values) + "]"


def query_fields(spec: dict, key: str) -> list[str]:
    cfg = COMMANDS[key]
    venues = list(cfg["venues"])
    op = operation(spec, key, venues[0])
    names = {p["name"] for p in op.get("parameters", [])}
    lines = []
    for arg in cfg["args"]:
        lines.append(f"    {arg}: str = Field(description={ARG_HELP[arg]!r})")
    if len(venues) > 1:
        lines.append(
            f"    venue: {lit(venues)} = Field(default={venues[0]!r}, description=VENUE_HELP)"
        )
    if "start" in names:
        lines.append("    start_date: date | datetime | None = Field(default=None, description=START_HELP)")
        lines.append("    end_date: date | datetime | None = Field(default=None, description=END_HELP)")
    defaults = cfg.get("defaults", {})
    for param in op.get("parameters", []):
        name = param["name"]
        if name in SKIP_PARAMS or name in cfg["args"] or param.get("in") == "path" or name in cfg.get("hidden", ()):
            continue
        schema = resolve(spec, param.get("schema", {}))
        desc = (param.get("description") or human(name)).split("\n")[0].strip()
        desc = re.sub(r"`", "", desc)[:300]
        enum = schema.get("enum")
        kind = schema.get("type")
        if enum:
            typ = lit(enum)
            if name == "interval" and not param.get("required") and name in defaults:
                typ = lit(["raw", *enum])
                desc += " raw returns every update."
        else:
            typ = {"integer": "int", "number": "float", "boolean": "bool"}.get(kind, "str")
        if name in defaults:
            lines.append(f"    {name}: {typ} = Field(default={defaults[name]!r}, description={desc!r})")
        elif param.get("required"):
            lines.append(f"    {name}: {typ} = Field(description={desc!r})")
        else:
            lines.append(f"    {name}: {typ} | None = Field(default=None, description={desc!r})")
    if "limit" in names:
        limit_param = next(p for p in op["parameters"] if p["name"] == "limit")
        page_max = resolve(spec, limit_param.get("schema", {})).get("maximum") or 1000
        paged = cfg.get("paged", True) and not cfg.get("single")
        cap = 1_000_000 if paged else page_max
        default = min(1000, cap)
        if cfg.get("limit"):
            default, cap = cfg["limit"]
        unit = "snapshots" if cfg.get("explode") else "records"
        lines.append(
            f"    limit: int = Field(default={default}, ge=1, le={cap}, description='The most {unit} to return.')"
        )
    return lines


def data_fields(spec: dict, key: str, samples: dict) -> list[str]:
    cfg = COMMANDS[key]
    docs: dict = {}
    for venue in cfg["venues"]:
        docs.update({k: v for k, v in spec_fields(spec, operation(spec, key, venue)).items() if k not in docs})
    kinds = samples.get(key, {})
    if not kinds:
        kinds = {name: "str" for name in docs}
    lines = []
    for name, kind in sorted(kinds.items(), key=lambda item: (item[0] != "date", item[0] != "symbol", item[0])):
        if not name.isidentifier() or keyword.iskeyword(name) or name in {"model_config", "schema", "copy", "json", "dict"}:
            continue
        base = name.split("_", 1)[1] if name.startswith(("order_", "level_")) and name.split("_", 1)[1] in docs else name
        desc = docs.get(base) or docs.get(name) or human(name)
        if name == "date":
            desc = "When the record was taken."
        lines.append(f"    {name}: {py_type(kind, name)} = Field(default=None, description={desc[:240]!r})")
    return lines or ["    pass"]


HEADER = '''"""Generated by codegen/generate.py from the 0xArchive OpenAPI spec. Do not edit by hand."""

# ruff: noqa: E501

from datetime import date, datetime
from typing import Any, Literal

from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.abstract.query_params import QueryParams
from pydantic import Field

from openbb_oxarchive.utils.base import OxarchiveData
from openbb_oxarchive.utils.engine import run

VENUE_HELP = "Where the market trades: hyperliquid (perps), lighter, hip3 (Hyperliquid builder-deployed perps), hip4 (Hyperliquid outcome markets), spot (Hyperliquid spot) or rh-lighter (Lighter on Robinhood Chain)."
START_HELP = "Start of the range. Defaults to 24 hours ago."
END_HELP = "End of the range, inclusive of a bare date. Defaults to now."
'''

FETCHER = '''

class {cls}QueryParams(QueryParams):
    """{title}."""

{qfields}


class {cls}Data(OxarchiveData):
    """{title}."""

{dfields}


class {cls}Fetcher(Fetcher[{cls}QueryParams, list[{cls}Data]]):
    """{title}."""

    require_credentials = True

    @staticmethod
    def transform_query(params: dict[str, Any]) -> {cls}QueryParams:
        return {cls}QueryParams(**params)

    @staticmethod
    async def aextract_data(query: {cls}QueryParams, credentials: dict[str, str] | None, **kwargs: Any) -> list[dict]:
        return await run({key!r}, query, credentials, page_max={page_max})

    @staticmethod
    def transform_data(query: {cls}QueryParams, data: list[dict], **kwargs: Any) -> list[{cls}Data]:
        return [{cls}Data.model_validate(row) for row in data]
'''


def write_models(spec: dict, samples: dict) -> None:
    parts = [HEADER]
    for key, cfg in COMMANDS.items():
        op = operation(spec, key, next(iter(cfg["venues"])))
        limit = next((p for p in op.get("parameters", []) if p["name"] == "limit"), None)
        page_max = resolve(spec, limit.get("schema", {})).get("maximum") if limit else None
        parts.append(
            FETCHER.format(
                cls=camel(key),
                title=cfg["title"],
                qfields="\n".join(query_fields(spec, key)) or "    pass",
                dfields="\n".join(data_fields(spec, key, samples)),
                key=key,
                page_max=page_max,
            )
        )
    parts.append("\n\nFETCHERS = {\n" + "".join(f"    {camel(k)!r}: {camel(k)}Fetcher,\n" for k in COMMANDS) + "}\n")
    (ROOT / "openbb_oxarchive" / "models" / "generated.py").write_text("".join(parts))


def example(cfg: dict, samples_ids: dict) -> str:
    params = {}
    for arg in cfg["args"]:
        params[arg] = {"symbol": "BTC", "user": "0x84eec0068b37919cc8f13d7454073ac167374cc0", "address": "0x84eec0068b37919cc8f13d7454073ac167374cc0", "account": "0x84eec0068b37919cc8f13d7454073ac167374cc0"}[arg]
    first = next(iter(cfg["venues"]))
    if first == "hip3" and "symbol" in params:
        params["symbol"] = "xyz:NVDA"
    if first == "spot" and "symbol" in params:
        params["symbol"] = "HYPE"
    if len(cfg["venues"]) > 1:
        params["venue"] = first
    if cfg["name"] == "lighter_accounts":
        params["l1_address"] = "0x0000000000000000000000000000000000000000"
    params["provider"] = "oxarchive"
    return f"APIEx(description={cfg['title']!r}, parameters={params!r})"


def write_router() -> None:
    groups: dict = {}
    for key, cfg in COMMANDS.items():
        groups.setdefault(cfg["group"], []).append((key, cfg))
    out = [
        '"""Generated by codegen/generate.py. Do not edit by hand."""\n\n# ruff: noqa: E501\n\n',
        "from openbb_core.app.model.command_context import CommandContext\n",
        "from openbb_core.app.model.example import APIEx\n",
        "from openbb_core.app.model.obbject import OBBject\n",
        "from openbb_core.app.provider_interface import ExtraParams, ProviderChoices, StandardParams\n",
        "from openbb_core.app.query import Query\n",
        "from openbb_core.app.router import Router\n\n",
        'router = Router(prefix="", description="Hyperliquid and Lighter market data from 0xArchive.")\n',
    ]
    for group, items in groups.items():
        var = f"{group}_router"
        out.append(f'\n{var} = Router(prefix="/{group}", description={GROUP_TITLES[group]!r})\n')
        for key, cfg in items:
            widget = {
                "name": cfg["title"].split(":")[0].replace(", one row per price level per snapshot", "").replace(", one row per price level", "") + " (0xArchive)",
                "description": cfg["title"] + ".",
                "category": "Crypto",
                "subCategory": GROUP_TITLES[group],
                "source": ["0xArchive"],
            }
            out.append(
                f"\n\n@{var}.command(\n    model={camel(key)!r},\n    widget_config={widget!r},\n    examples=[{example(cfg, {})}],\n)\n"
                f"async def {cfg['name']}(\n    cc: CommandContext,\n    provider_choices: ProviderChoices,\n    standard_params: StandardParams,\n    extra_params: ExtraParams,\n) -> OBBject:\n"
                f'    """{cfg["title"]}."""\n    return await OBBject.from_query(Query(**locals()))\n'
            )
        out.append(f"\n\nrouter.include_router({var})\n")
    (ROOT / "openbb_oxarchive" / "oxarchive_router.py").write_text("".join(out))


def main() -> None:
    spec = load_spec("--refresh-spec" in sys.argv)
    api_key = os.environ.get("OXARCHIVE_API_KEY")
    if api_key and "--offline" not in sys.argv:
        only = {a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")}
        only = set().union(*(o.split(",") for o in only)) if only else None
        samples = collect_samples(spec, api_key, only)
        SAMPLES_PATH.write_text(json.dumps(samples, indent=1, sort_keys=True) + "\n")
    else:
        samples = json.loads(SAMPLES_PATH.read_text())
    write_models(spec, samples)
    write_router()
    print("wrote models/generated.py and oxarchive_router.py for", len(COMMANDS), "commands")


if __name__ == "__main__":
    main()
