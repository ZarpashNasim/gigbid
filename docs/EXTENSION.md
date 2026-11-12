# Signature extension

TODO: choose one extension from the assignment and document its design and evaluation here. Candidate
directions grounded in this codebase (pick one and go deep, with a measured result that traces to
`evals/results/`):

- **Semantic support grader** to replace the strict-lexical V8 grader, which over-abstains (see
  `docs/RESULTS.md`). Measure the change in V8 coverage/abstain on the synthetic dev set.
- **Outcome-aware reranking (V4)** tuned on past-proposal outcomes (won/replied/ignored) with an ablation.
- **Style memory**: promote the freelancer's accepted edits into the LangGraph store and show it changes
  later drafts (`agent/memory/promotion_rules.py`).
- **Live-Upwork adapter** behind the existing `MarketplacePort` (design only unless credentials are
  available), reusing the GigSim contract.

State the hypothesis, the before/after measurement, and the honest limitation.
