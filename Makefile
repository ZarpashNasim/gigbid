.PHONY: test eval eval-synth synth card lint dev seed demo gigsim
test:
	python -m pytest tests mcp_servers -q

# Self-built GigSim marketplace simulator (stand-in; the instructor's service was not in the kit).
# Serves data/synthetic over HTTP on :8081 with bearer auth, a 20/min rate limit and simulated client replies.
# See gigsim/README.md. Set GIGSIM_API_TOKEN in .env for a non-default token.
gigsim:
	python -m gigsim

# Reruns the full variant comparison + ablation and rewrites evals/results/*.json (+ .md tables).
# Point DATASET at the real dev set from the starter kit; the toy set only validates the machinery.
DATASET ?= evals/datasets/toy_dev.json
CORPUS  ?= data/sample/portfolio.json
eval:
	python -m evals.runners.rag_eval --corpus $(CORPUS) --dataset $(DATASET) --out evals/results/rag_results.json
	python -m evals.runners.ablation --corpus $(CORPUS) --dataset $(DATASET) --out evals/results/ablation.json

# Deterministic synthetic data + gold labels (instructor data is NOT in the kit; this is our stand-in).
synth:
	python -m gigdata.synth
card:
	python -m gigdata.card

# Dev-split evaluation on synthetic data. Holdout is run once, manually: make eval-holdout
eval-synth:
	python -m evals.runners.rag_eval --dataset evals/datasets/synth_retrieval_dev.json --out evals/results/rag_synth_dev.json
	python -m evals.runners.ablation --dataset evals/datasets/synth_retrieval_dev.json --out evals/results/ablation_synth_dev.json
	python -m evals.runners.baseline_decision --split dev
	python -m evals.runners.intent_eval --split dev
eval-holdout:
	python -m evals.runners.rag_eval --dataset evals/datasets/synth_retrieval_holdout.json --out evals/results/rag_synth_holdout.json
	python -m evals.runners.ablation --dataset evals/datasets/synth_retrieval_holdout.json --out evals/results/ablation_synth_holdout.json
	python -m evals.runners.baseline_decision --split holdout
	python -m evals.runners.intent_eval --split holdout
