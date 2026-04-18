PYTHON=python
UV=$(PYTHON) -m uv

.PHONY: sync run test lint format

sync:
	$(UV) sync --extra dev

run:
	$(UV) run polybot

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

