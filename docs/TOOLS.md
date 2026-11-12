# Tool inventory

| Tool | Server | R/W | Annotations | Auth |
|---|---|---|---|---|
| search_evidence | portfolio | read | readOnly, idempotent | local / none |
| get_case_study | portfolio | read | readOnly, idempotent | local / none |
| list_skills | portfolio | read | readOnly, idempotent | local / none |
| search_jobs, get_job, get_client_history, get_connects_balance, list_messages | marketplace | read | readOnly, idempotent | bearer token |
| create_proposal_draft | marketplace | write | non-destructive, idempotent (key) | bearer token |
| submit_proposal, send_message | marketplace | write | destructive, idempotent (key) | bearer token |

All writes default to `dry_run=true`. TODO: workspace server, official Upwork MCP, GitHub MCP.

## Third-party servers (trust rationale, one line each)
- Official Upwork MCP (mcp.upwork.com): first-party server run by the marketplace; OAuth 2.1; every write is a draft the user confirms on Upwork.
- GitHub MCP: TODO. Read-only token scoped to the user's own repos.
