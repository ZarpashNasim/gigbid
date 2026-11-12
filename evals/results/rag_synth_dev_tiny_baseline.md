| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.378 | 0.583 | 0.875 | 0.654 | n/a | 2.2 |
| V1 decompose (naive reqs) | 0.315 | 0.667 | 0.667 | 0.597 | n/a | 0.2 |
| V1 decompose (oracle reqs) | 0.305 | 0.646 | 0.800 | 0.618 | n/a | 0.1 |
| V2 hybrid | 0.440 | 0.708 | 1.000 | 0.686 | n/a | 0.3 |
| V3 hybrid+rerank | 0.405 | 0.625 | 0.875 | 0.702 | n/a | 0.6 |
| V4 outcome-aware | 0.321 | 0.458 | 0.792 | 0.678 | n/a | 1.7 |
| V8 corrective | 0.250 | 0.375 | 0.500 | 0.324 | n/a | 10.1 |
