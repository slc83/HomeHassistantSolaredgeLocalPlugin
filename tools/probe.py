#!/usr/bin/env python3
"""Read the inverter without installing Home Assistant or dependencies."""

import argparse
import asyncio
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / "custom_components/solaredge_local/client.py"
spec = importlib.util.spec_from_file_location("solaredge_client", path)
client = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = client
spec.loader.exec_module(client)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Indirizzo IP o hostname dell'inverter")
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--unit-id", type=int, default=1)
    args = parser.parse_args()
    try:
        result = await client.SolarEdgeClient(
            args.host, args.port, args.unit_id
        ).async_poll()
    except client.SolarEdgeError as err:
        parser.exit(1, f"Errore: {err}\n")
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
