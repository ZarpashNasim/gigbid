| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.432 | 0.696 | 0.701 | 0.616 | 0.00 | 0.2 |
| V1 decompose (naive reqs) | 0.363 | 0.621 | 0.630 | 0.582 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.411 | 0.661 | 0.725 | 0.615 | 0.00 | 0.1 |
| V2 hybrid | 0.473 | 0.776 | 0.804 | 0.679 | 0.00 | 0.3 |
| V3 hybrid+rerank | 0.529 | 0.796 | 0.804 | 0.712 | 0.00 | 3.2 |
| V4 outcome-aware | 0.494 | 0.737 | 0.797 | 0.695 | 0.00 | 2.5 |
| V8 corrective | 0.139 | 0.221 | 0.415 | 0.194 | 0.75 | 5.3 |
