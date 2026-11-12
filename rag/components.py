"""Factory that turns CLI/eval strings into real retrieval components, and names them for the result `meta`.

Keeps the eval runners free of provider details and keeps the default path on the offline placeholders, so tests/CI
still run with no network. `.env` is loaded here (if python-dotenv is present) so OPENROUTER_API_KEY / GROQ_API_KEY
reach the LLM client.

  embedder spec : "hash" (default, placeholder)            | "ollama[:model]"  (default model nomic-embed-text)
  reranker spec : "lexical" (default, stand-in)            | "llm"             (listwise LLM reranker)
  grader  spec  : "lexical" (default, V8 strict overlap)   | "llm"            (LLM support grader)

All LLM components share one agent.llm.OpenAICompatLLM built from agent/config.yaml's active profile.
"""
from __future__ import annotations

import os

from rag.index.store import HashEmbedder, OllamaEmbedder
from rag.stages import LexicalReranker, LLMReranker, LLMSupportGrader, SemanticSupportGrader


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()                      # reads ./.env if present; never overrides already-set vars


def make_llm(profile: str | None = None):
    """Build the shared LLM from agent/config.yaml. Returns None if the active profile's API key env var is unset,
    so LLM components transparently fall back to their lexical stand-ins instead of crashing."""
    from agent.config import load_config
    from agent.llm import OpenAICompatLLM

    cfg = dict(load_config())
    if profile:
        cfg["active_profile"] = profile
    p = cfg["profiles"][cfg["active_profile"]]
    if not os.environ.get(p["api_key_env"]):
        return None, f"{p.get('provider', cfg['active_profile'])}(NO KEY in {p['api_key_env']})"
    return OpenAICompatLLM(cfg), f"{p.get('provider', cfg['active_profile'])}:{p['nodes']['small']}"


def make_embedder(spec: str | None):
    """-> (embedder_or_None, name). None means Corpus uses its default HashEmbedder."""
    if not spec or spec == "hash":
        return None, "HashEmbedder(stand-in)"
    if spec.startswith("ollama"):
        model = spec.split(":", 1)[1] if ":" in spec else "nomic-embed-text"
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OllamaEmbedder(model=model, host=host), f"ollama:{model}"
    raise SystemExit(f"unknown embedder spec: {spec!r} (use 'hash' or 'ollama[:model]')")


def make_reranker(spec: str | None, llm=None):
    if not spec or spec == "lexical":
        return LexicalReranker(), "LexicalReranker(stand-in)"
    if spec == "llm":
        return LLMReranker(llm=llm), "LLMReranker" + ("" if llm else "(no key -> lexical fallback)")
    raise SystemExit(f"unknown reranker spec: {spec!r} (use 'lexical' or 'llm')")


def make_grader(spec: str | None, llm=None, embedder=None, threshold: float = 0.60):
    """V8 support grader. -> (grader_or_None, name). None = V8's built-in strict lexical check.

    semantic: embedding-cosine grader (the signature extension). Pass the retriever's embedder so it reuses the
    same model; with the hash stand-in it stays lexical (named as a stand-in), with Ollama it is a real
    semantic grader."""
    if not spec or spec == "lexical":
        return None, "V8 grader (lexical)"
    if spec == "llm":
        if llm is None:
            return None, "V8 grader (lexical; no key)"
        return LLMSupportGrader(llm=llm), "LLMSupportGrader"
    if spec == "semantic":
        tag = "hash stand-in" if (embedder is None or type(embedder).__name__ == "HashEmbedder") else "ollama"
        return SemanticSupportGrader(embedder=embedder, threshold=threshold), f"SemanticSupportGrader({tag}, thr={threshold})"
    raise SystemExit(f"unknown grader spec: {spec!r} (use 'lexical' | 'llm' | 'semantic')")
