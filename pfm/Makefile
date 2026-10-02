.PHONY: run test lint seed train evaluate migrate run-api

run:
	docker compose up --build

test:
	cd backend && python -m pytest

lint:
	cd backend && python -m ruff check app tests && python -m black --check app tests alembic && python -m mypy app

seed:
	cd backend && python -m app.cli seed

train:
	cd backend && python -m app.cli train

evaluate:
	cd backend && python -m app.cli evaluate

migrate:
	cd backend && python -m alembic upgrade head

run-api:
	cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
