"""Call every command on every venue through OpenBB against the real API.

    OXARCHIVE_API_KEY=... python codegen/live_sweep.py [--json out.json]

Exits non-zero if any call fails for a reason other than the market having no data
in the window. Run it after regenerating, and on a schedule to catch drift.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "codegen"))

from generate import sample_args  # noqa: E402

from openbb_oxarchive.registry import COMMANDS  # noqa: E402


def main() -> int:
    from openbb import obb

    key = os.environ["OXARCHIVE_API_KEY"]
    obb.user.credentials.oxarchive_api_key = key
    ids = sample_args(key)
    calls = []
    after = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--after=")), None)
    skipping = after is not None
    for name, cfg in COMMANDS.items():
        if skipping:
            skipping = name != after
            continue
        for venue in cfg["venues"]:
            params: dict = {}
            for arg in cfg["args"]:
                pick = ids["symbol"] if arg == "symbol" else ids["account"] if arg == "account" else ids["user"] if name.startswith("twap") else ids["address"]
                params[arg] = pick[venue] if isinstance(pick, dict) else pick
            if len(cfg["venues"]) > 1:
                params["venue"] = venue
            if name == "lighter_accounts":
                continue
            if name not in {"instruments", "spot_pairs", "positioning", "wallet_account"} and not cfg.get("single"):
                params["limit"] = min(20, cfg.get("limit", (20, 20))[0])
            fn = getattr(getattr(obb.oxarchive, cfg["group"]), cfg["name"])
            calls.append((f"oxarchive.{cfg['group']}.{cfg['name']} [{venue}]", fn, params))
    calls += [
        ("crypto.price.historical [lighter]", obb.crypto.price.historical, {"symbol": "ETH", "venue": "lighter", "provider": "oxarchive", "interval": "1h"}),
        ("crypto.search", obb.crypto.search, {"query": "nvda", "provider": "oxarchive"}),
    ]
    if hasattr(obb, "derivatives"):
        calls += [
            ("derivatives.futures.historical", obb.derivatives.futures.historical, {"symbol": "BTC", "provider": "oxarchive"}),
            ("derivatives.futures.instruments [lighter]", obb.derivatives.futures.instruments, {"provider": "oxarchive", "venue": "lighter"}),
        ]

    results = []
    for label, fn, params in calls:
        started = time.time()
        try:
            frame = fn(**params).to_df()
            results.append({"call": label, "ok": True, "rows": len(frame), "columns": len(frame.columns), "seconds": round(time.time() - started, 1)})
        except Exception as error:  # noqa: BLE001
            text = str(error).strip().replace("\n", " ")[:220]
            empty = "no rows" in text.lower() or "no data" in text.lower() or "No results" in text
            results.append({"call": label, "ok": False, "empty": empty, "error": text, "seconds": round(time.time() - started, 1)})
        status = results[-1]
        print(("PASS " if status["ok"] else "EMPTY" if status.get("empty") else "FAIL ") + f" {label} " + (f"{status.get('rows')} rows" if status["ok"] else status["error"]), flush=True)

    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(results, indent=1))
    failed = [r for r in results if not r["ok"] and not r.get("empty")]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed or empty, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
