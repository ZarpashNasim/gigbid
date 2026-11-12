| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.068 | 0.142 | 0.171 | 0.137 | 0.00 | 0.1 |
| V1 decompose (naive reqs) | 0.072 | 0.154 | 0.164 | 0.117 | 0.00 | 0.2 |
| V1 decompose (oracle reqs) | 0.144 | 0.295 | 0.347 | 0.240 | 0.00 | 0.1 |
| V2 hybrid | 0.078 | 0.159 | 0.191 | 0.164 | 0.00 | 0.3 |
| V3 hybrid+rerank | 0.144 | 0.257 | 0.252 | 0.226 | 0.00 | 1.1 |
| V4 outcome-aware | 0.111 | 0.223 | 0.160 | 0.203 | 0.00 | 3.5 |
| V8 corrective | 0.094 | 0.166 | 0.149 | 0.101 | 0.46 | 9.1 |
