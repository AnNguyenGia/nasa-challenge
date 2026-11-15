PYTHON ?= python
.PHONY: dev test seed migrate models
dev:
	$(PYTHON) -m app.cli serve
test:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ruff check app scripts migrations tests
	$(PYTHON) -m mypy --strict app
seed:
	$(PYTHON) -m app.cli seed
migrate:
	$(PYTHON) -m alembic upgrade head
models:
	$(PYTHON) scripts/build_demo_models.py
