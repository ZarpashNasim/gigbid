| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.388 | 0.653 | 0.771 | 0.623 | 0.00 | 2.6 |
| V1 decompose (naive reqs) | 0.336 | 0.576 | 0.665 | 0.576 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.418 | 0.632 | 0.672 | 0.556 | 0.00 | 0.1 |
| V2 hybrid | 0.460 | 0.799 | 0.840 | 0.673 | 0.00 | 0.3 |
| V3 hybrid+rerank | 0.523 | 0.792 | 0.757 | 0.683 | 0.00 | 1.3 |
| V4 outcome-aware | 0.434 | 0.694 | 0.674 | 0.636 | 0.00 | 1.7 |
| V8 corrective | 0.156 | 0.250 | 0.333 | 0.200 | 0.75 | 13.3 |
