"""GigSim: a self-built local marketplace simulator.

NOT the instructor's GigSim. This is a faithful-enough stand-in so GigBid can run, be demoed and be
tested end-to-end over HTTP (the real GigSim service was not provided with the starter kit). It serves the
synthetic jobs/clients/threads through the same REST surface the marketplace adapter expects, enforces bearer
auth and a published rate limit, tracks Connects, and — unlike the offline SyntheticBackend — generates
deterministic simulated client replies. Replace it with the official GigSim if that service is ever supplied;
nothing else in the system changes (that is the point of the marketplace port).
"""
from .app import build_gigsim

__all__ = ["build_gigsim"]
