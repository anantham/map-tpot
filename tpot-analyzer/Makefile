SHELL := /bin/bash

VENV_PY ?= .venv/bin/python
PYTEST ?= $(VENV_PY) -m pytest

.DEFAULT_GOAL := help

.PHONY: help ensure-venv verify-louvain-contract verify-baseline test-smoke test-ci test verify-docs deploy-public-site

help:
	@echo "Available targets:"
	@echo "  make verify-louvain-contract  # verify python-louvain pin + import contract"
	@echo "  make verify-baseline          # run non-deploying baseline contract checks"
	@echo "  make test-smoke               # run fast backend smoke tests"
	@echo "  make test-ci                  # run the credential-free backend CI suite"
	@echo "  make test                     # run the full backend test suite"
	@echo "  make verify-docs              # run docs hygiene verification"
	@echo "  make deploy-public-site       # [DANGER] Run bootstrap prop + export + blob upload"

ensure-venv:
	@test -x "$(VENV_PY)" || (echo "Missing $(VENV_PY). Run: python3.11 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt" && exit 1)

verify-louvain-contract: ensure-venv
	@$(VENV_PY) -m scripts.verify_louvain_dependency_contract

verify-baseline: ensure-venv
	@$(VENV_PY) -m scripts.verify_assumption_baseline
	@$(VENV_PY) -m scripts.verify_louvain_dependency_contract
	@$(VENV_PY) -m scripts.verify_docs_hygiene
	@$(VENV_PY) -m scripts.verify_api_contracts
	@$(VENV_PY) -m scripts.verify_clusters --base-path tests/fixtures/medium_graph/graph_snapshot --granularity 25
	@$(VENV_PY) -m scripts.verify_clusters --base-path tests/fixtures/medium_graph/graph_snapshot --granularity 40

test-smoke: ensure-venv
	@$(PYTEST) tests/test_spectral.py tests/test_clusters.py -q

test-ci: ensure-venv
	@$(PYTEST) tests -m 'not selenium and not requires_supabase' -q --tb=short --maxfail=20

test: ensure-venv
	@$(PYTEST) -q --maxfail=20

verify-docs:
	@python3 -m scripts.verify_docs_hygiene

deploy-public-site: ensure-venv
	@echo "--- 1/3: Running Bootstrap Propagation (5 iters) ---"
	@$(VENV_PY) -m scripts.propagate_community_labels --save --bootstrap 5 --mode independent
	@echo "--- 2/3: Exporting Data for Public Site ---"
	@$(VENV_PY) -m scripts.export_public_site
	@echo "--- 3/3: Uploading to Vercel Blob ---"
	@cd public-site && node scripts/upload-public-site-data.mjs
	@echo "Deployment complete."
