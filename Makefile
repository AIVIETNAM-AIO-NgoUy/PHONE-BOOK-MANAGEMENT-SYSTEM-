PYTHON ?= $(shell which ./venv/bin/python 2>/dev/null || which python3)
PYTEST ?= $(shell which ./venv/bin/pytest 2>/dev/null || which pytest)
FLAKE8 ?= $(shell which ./venv/bin/flake8 2>/dev/null || which flake8)
BLACK ?= $(shell which ./venv/bin/black 2>/dev/null || which black)
ISORT ?= $(shell which ./venv/bin/isort 2>/dev/null || which isort)

.PHONY: help dev test test-cov lint format migrate seed db-dump db-restore docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make dev         - Run Django development server"
	@echo "  make test        - Run test suite"
	@echo "  make test-cov    - Run pytest with coverage report"
	@echo "  make lint        - Run flake8, black check, and isort check"
	@echo "  make format      - Auto-format code with black and isort"
	@echo "  make migrate     - Run database migrations"
	@echo "  make seed        - Seed demo accounts"
	@echo "  make db-dump     - Dump database to backups/phonebook_db.sql"
	@echo "  make db-restore  - Restore database from backups/phonebook_db.sql"
	@echo "  make docker-up   - Build and start Docker containers"
	@echo "  make docker-down - Stop Docker containers"

dev:
	cd backend && $(PYTHON) manage.py runserver

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=backend/apps --cov-report=term-missing

lint:
	$(FLAKE8) backend/
	$(BLACK) --check backend/
	$(ISORT) --check-only backend/

format:
	$(BLACK) backend/
	$(ISORT) backend/

migrate:
	cd backend && $(PYTHON) manage.py migrate

seed:
	cd backend && $(PYTHON) manage.py seed_demo_accounts

db-dump:
	./scripts/backup_restore.sh --dump backups/phonebook_db.sql

db-restore:
	./scripts/backup_restore.sh --restore backups/phonebook_db.sql

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down
