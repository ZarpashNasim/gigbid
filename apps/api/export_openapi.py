"""Write openapi.json (used to generate the typed TS client). Run: python -m apps.api.export_openapi"""
import json
import sys
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver

from agent.config import load_config
from apps.api.main import create_app

if __name__ == "__main__":
    deps = SimpleNamespace(cfg=load_config(), llm=None, market=None, retriever=None, store=None)
    out = sys.argv[1] if len(sys.argv) > 1 else "apps/web/openapi.json"
    json.dump(create_app(deps, InMemorySaver(), {}).openapi(), open(out, "w"), indent=2)
    print("wrote", out)
