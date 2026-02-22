SHELL := /bin/bash

VENV_PY ?= .venv/bin/python
PYTEST ?= $(VENV_PY) -m pytest

.DEFAULT_GOAL := help

.PHONY: help ensure-venv verify-louvain-contract test-smoke test verify-docs

help:
	@echo "Available targets:"
	@echo "  make verify-louvain-contract  # verify python-louvain pin + import contract"
	@echo "  make test-smoke               # run fast backend smoke tests"
	@echo "  make test                     # run full backend test suite"
	@echo "  make verify-docs              # run docs hygiene verification"

ensure-venv:
	@test -x "$(VENV_PY)" || (echo "Missing $(VENV_PY). Run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt" && exit 1)

verify-louvain-contract: ensure-venv
	@$(VENV_PY) -m scripts.verify_louvain_dependency_contract

test-smoke: ensure-venv
	@$(PYTEST) tests/test_spectral.py tests/test_clusters.py -q

test: ensure-venv
	@$(PYTEST) -q --maxfail=20

verify-docs:
	@python3 -m scripts.verify_docs_hygiene
