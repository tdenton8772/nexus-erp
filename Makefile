.PHONY: up down dev migrate seed lint test

up:
	docker compose up -d

down:
	docker compose down

dev:
	uvicorn backend.main:app --reload --port 8000

migrate:
	alembic upgrade head

seed:
	python scripts/bootstrap_connectors.py

lint:
	ruff check backend/ && mypy backend/

test:
	pytest tests/ -v

generate-fernet-key:
	python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
