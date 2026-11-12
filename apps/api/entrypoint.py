"""Production wiring from environment variables.   uvicorn --factory apps.api.entrypoint:build_app"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from langgraph.store.memory import InMemoryStore

from agent.checkpointing import make_checkpointer
from agent.config import load_config
from agent.deps import Deps
from agent.llm import OpenAICompatLLM
from agent.marketplace_port import BackendPort
from apps.api.events import EventLog
from apps.api.main import create_app
from mcp_servers.marketplace.adapters.gigsim import GigSimBackend
from mcp_servers.marketplace.adapters.synthetic import SyntheticBackend
from agent.workspace import InMemoryWorkspace
from rag.index.store import Corpus
from rag.retriever import get_retriever


def build_app():
    cfg = load_config()
    persona = os.environ.get("PERSONA", "ai_engineer")
    mode = os.environ.get("MARKETPLACE_MODE", "gigsim")          # gigsim | synthetic (offline stand-in; NOT GigSim)
    default_portfolio = f"data/synthetic/personas/{persona}/portfolio.json" if mode == "synthetic" else "data/sample/portfolio.json"
    # evidence index = verified work only; past proposals are claims and stay out of it.
    # EMBEDDER (hash default | ollama[:model]) + OLLAMA_HOST are read by make_embedder.
    from rag.components import make_embedder
    embedder, _ = make_embedder(os.environ.get("EMBEDDER", "hash"))
    corpus = Corpus.from_json(os.environ.get("PORTFOLIO_PATH", default_portfolio),
                              eligible_only=True, **({"embedder": embedder} if embedder else {}))
    gigsim_url = os.environ.get("GIGSIM_BASE_URL") or os.environ.get("GIGSIM_URL", "http://localhost:8081")
    gigsim_token = os.environ.get("GIGSIM_API_TOKEN") or os.environ.get("GIGSIM_API_KEY", "")
    backend = (SyntheticBackend(os.environ.get("SYNTHETIC_DIR", "data/synthetic"), os.environ.get("SYNTHETIC_SPLIT", "dev"))
               if mode == "synthetic" else GigSimBackend(gigsim_url, gigsim_token))
    profiles = {}
    if mode == "synthetic":
        prof = json.loads(open(f"data/synthetic/personas/{persona}/freelancer.json").read())
        profiles = {u: prof for u in json.loads(os.environ.get("API_TOKENS", "{}")).values()}
    deps = Deps(
        llm=OpenAICompatLLM(cfg),
        market=BackendPort(backend),
        workspace=InMemoryWorkspace(),
        profiles=profiles,
        retriever=get_retriever(os.environ.get("RAG_VARIANT", "v2_hybrid"), corpus),
        store=InMemoryStore(),          # TODO: Postgres-backed store so style memory survives restarts
        cfg=cfg,
    )
    tokens = json.loads(os.environ.get("API_TOKENS", "{}"))     # {"token": "user_id"}; replace with real auth
    return create_app(deps, make_checkpointer(), tokens,
                      registry_path=os.environ.get("REGISTRY_DB", "registry.db"),
                      events=EventLog(os.environ.get("EVENTS_DB", "events.db")),
                      executor=ThreadPoolExecutor(max_workers=4))
