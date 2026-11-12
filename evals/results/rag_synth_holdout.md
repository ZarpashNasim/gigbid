| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.390 | 0.644 | 0.669 | 0.610 | 0.00 | 0.1 |
| V1 decompose (naive reqs) | 0.361 | 0.628 | 0.661 | 0.586 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.407 | 0.691 | 0.663 | 0.605 | 0.00 | 0.1 |
| V2 hybrid | 0.438 | 0.739 | 0.835 | 0.680 | 0.00 | 0.2 |
| V3 hybrid+rerank | 0.488 | 0.767 | 0.824 | 0.701 | 0.00 | 0.7 |
| V4 outcome-aware | 0.515 | 0.781 | 0.832 | 0.729 | 0.00 | 1.9 |
| V8 corrective | 0.160 | 0.262 | 0.534 | 0.228 | 0.67 | 4.0 |
