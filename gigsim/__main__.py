"""Run the GigSim simulator.   py -m gigsim

Reads from the environment (with starter-kit-compatible names):
  GIGSIM_API_TOKEN   bearer token clients must present     (default: dev-local-token)
  GIGSIM_PORT        port to listen on                     (default: 8081, per the starter kit)
  GIGSIM_DATA_DIR    synthetic data root                   (default: data/synthetic)
  GIGSIM_SPLIT       dev | holdout                         (default: dev)
  GIGSIM_CONNECTS    starting Connects balance             (default: 200)
  GIGSIM_RATE_PER_MIN  requests/min per token              (default: 20, per the starter kit)
"""
from __future__ import annotations

import os

import uvicorn

from .app import DEV_TOKEN, build_gigsim


def main() -> None:
    token = os.environ.get("GIGSIM_API_TOKEN") or os.environ.get("GIGSIM_API_KEY") or DEV_TOKEN
    port = int(os.environ.get("GIGSIM_PORT", "8081"))
    app = build_gigsim(
        data_dir=os.environ.get("GIGSIM_DATA_DIR", "data/synthetic"),
        split=os.environ.get("GIGSIM_SPLIT", "dev"),
        token=token,
        connects=int(os.environ.get("GIGSIM_CONNECTS", "200")),
        per_minute=int(os.environ.get("GIGSIM_RATE_PER_MIN", "20")),
    )
    if token == DEV_TOKEN:
        print("GigSim: using the built-in dev token; set GIGSIM_API_TOKEN for anything shared.")
    host = os.environ.get("GIGSIM_HOST", "0.0.0.0")   # 0.0.0.0 so Docker port mapping / the API container can reach it
    print(f"GigSim (self-built stand-in) on http://{host}:{port}  split={os.environ.get('GIGSIM_SPLIT', 'dev')}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
