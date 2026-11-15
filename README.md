# mycatalogue – Multi-Tenant Digital Storefront SaaS

[![CI](https://github.com/mycatalogue/mycatalogue/actions/workflows/ci.yml/badge.svg)](https://github.com/mycatalogue/mycatalogue/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Django Version](https://img.shields.io/badge/django-5.1-green.svg)](https://www.djangoproject.com/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A production-ready multi-tenant SaaS application powering customizable digital storefronts for merchants. Built with a clean modular monolith architecture using Django, PostgreSQL, HTMX, and Tailwind CSS.

---

## Technology Stack

- **Backend:** Python 3.12, Django 5.1
- **Database:** PostgreSQL 16 (production & docker), SQLite (lightweight dev fallback)
- **Containerization:** Docker & Docker Compose
- **Frontend:** Django Templates, HTMX, Tailwind CSS
- **Testing & Quality:** Pytest, pytest-django, pytest-cov, Ruff
- **Configuration:** Twelve-Factor App via `django-environ`

---

## Quick Start with Docker (Recommended)

### 1. Clone & Configure Environment

```bash
git clone <repo-url> mycatalogue
cd mycatalogue
cp .env.example .env
```

### 2. Launch Application & Database

```bash
docker-compose up --build -d
```

The web service automatically awaits PostgreSQL database readiness, runs database migrations, and binds to `http://localhost:8000`.

### 3. Verify Health Check

Visit `http://localhost:8000/health/` or run:

```bash
curl http://localhost:8000/health/
# {"status": "healthy", "components": {"database": "healthy"}}
```

---

## Local Development (Without Docker)

### 1. Set Up Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements/development.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

### 3. Build Tailwind CSS

```bash
npm install
npm run build:css
# For automatic recompilation on file changes:
npm run watch:css
```

### 4. Run Migrations & Start Server

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

---

## Testing & Quality Assurance

```bash
# Run automated tests
pytest

# Run tests with test coverage
pytest --cov=apps --cov-report=term-missing

# Run Ruff linter
ruff check .

# Run Ruff formatter check
ruff format --check .

# Validate Django deployment checks
python manage.py check --deploy --settings=config.settings.production
```

---

## Project Structure

```
mycatalogue/
├── apps/               # Modular domain applications (core, merchants, catalog, etc.)
│   └── core/           # Foundation app, health check endpoint, base components
├── config/             # Project orchestration & URL routing
│   └── settings/       # Environment-separated settings (base, dev, staging, prod, test)
├── docker/             # Dockerfile & container entrypoint scripts
├── docs/               # System documentation & Architecture Decision Records (ADRs)
├── requirements/       # Split dependency specifications
├── static/             # Static assets (CSS source, compiled dist, vendored JS)
├── templates/          # Base HTML layouts and reusable components
├── docker-compose.yml  # Multi-container orchestration (Django + PostgreSQL)
└── pyproject.toml      # Configuration for pytest, ruff, and coverage
```

---

## Documentation Index

- [Architecture Overview](docs/architecture/overview.md)
- [ADR 0001: Project Foundation](docs/architecture/decisions/0001-project-foundation.md)
- [Local Setup Guide](docs/development/setup.md)
- [Docker Workflow Guide](docs/development/docker.md)
- [Testing & Quality Guide](docs/development/testing.md)
- [Engineering Guidelines](agent.md)

