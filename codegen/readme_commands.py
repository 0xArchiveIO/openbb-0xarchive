"""Print the README command reference from the registry. Pasted between the markers in README.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openbb_oxarchive.registry import COMMANDS  # noqa: E402

GROUPS = {
    "market": "Market data",
    "orderbook": "Order books",
    "liquidations": "Liquidations",
    "flow": "Order flow",
    "breadth": "Market breadth",
    "positions": "Positions",
    "wallets": "Wallets and accounts",
    "reference": "Reference",
}
SHORT = {"hyperliquid": "HL", "lighter": "Lighter", "hip3": "HIP-3", "hip4": "HIP-4", "spot": "Spot", "rh-lighter": "Lighter (Robinhood)"}

lines = []
for group, title in GROUPS.items():
    lines.append(f"### {title}\n")
    lines.append("| Command | What it returns | Venues |")
    lines.append("| --- | --- | --- |")
    for cfg in COMMANDS.values():
        if cfg["group"] != group:
            continue
        venues = ", ".join(SHORT[v] for v in cfg["venues"])
        lines.append(f"| `obb.oxarchive.{group}.{cfg['name']}` | {cfg['title']} | {venues} |")
    lines.append("")
print("\n".join(lines).rstrip())
