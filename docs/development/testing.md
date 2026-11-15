# Testing and Quality Assurance

`mycatalogue` uses **pytest** alongside **pytest-django**, **pytest-cov**, and **Ruff**.

## Running Tests

Execute pytest with test configuration:

```bash
# Run full test suite
pytest

# Run tests with coverage report
pytest --cov=apps --cov-report=term-missing

# Run a specific test module
pytest apps/core/tests/test_health_check.py
```

## Linting and Code Formatting

We use **Ruff** for sub-millisecond linting and code formatting conforming to PEP 8.

```bash
# Check code for lint errors
ruff check .

# Automatically fix fixable lint errors
ruff check --fix .

# Check code formatting
ruff format --check .

# Format code
ruff format .
```

## Django Deployment Check

Before deploying to staging or production, run Django's security and system check:

```bash
python manage.py check --deploy --settings=config.settings.production
```

