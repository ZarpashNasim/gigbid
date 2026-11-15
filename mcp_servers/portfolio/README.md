# Portfolio MCP server

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that exposes a freelancer's
portfolio as **tools**, **resources** and **prompts**, built on the official MCP Python SDK (FastMCP).
Source: [`server.py`](server.py).

## Capabilities

**Tools** (all read-only, annotated `readOnlyHint=true`):
- `search_evidence(requirement, k, type?, outcome?)` — retrieve portfolio evidence proving one requirement.
- `get_case_study(id)` — fetch one full portfolio item by id.
- `list_skills()` — every skill tagged in the portfolio.

**Resources:** `portfolio://case/{id}`, `portfolio://proposal/{id}` (JSON a host can load).

**Prompts:** `answer_screening_question(question)`, `draft_cover_letter(job_description)` — both force the
host to ground every claim in the evidence tools.

## Run it (stdio transport, for Claude Desktop / Cursor)

```bash
PORTFOLIO_PATH=data/sample/portfolio.json py -m mcp_servers.portfolio.server
```

Connect it from an MCP host by adding this to the host's MCP config (e.g. Claude Desktop
`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gigbid-portfolio": {
      "command": "py",
      "args": ["-m", "mcp_servers.portfolio.server"],
      "cwd": "/absolute/path/to/gigbid",
      "env": { "PORTFOLIO_PATH": "data/sample/portfolio.json" }
    }
  }
}
```

Then ask the host things like *"search my portfolio for RAG + pgvector evidence"* or invoke the
`draft_cover_letter` prompt — the server answers only from the portfolio, citing evidence ids.

## Notes
- Read-only by design: it never writes or sends anything.
- The sample portfolio (`data/sample/portfolio.json`) is illustrative synthetic data.
- Tests: `mcp_servers/` is covered by the project test suite (`py -m pytest -q`).
