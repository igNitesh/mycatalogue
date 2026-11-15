# Local Development Setup Guide

Follow this guide to run `mycatalogue` directly on your host machine without Docker.

## Prerequisites
- Python 3.12+
- Node.js 18+ and npm (for compiling Tailwind CSS)
- PostgreSQL 15+ (or SQLite for lightweight local testing)

## 1. Virtual Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

## 2. Install Dependencies

```bash
pip install -r requirements/development.txt
```

## 3. Environment Configuration

```bash
cp .env.example .env
```

Adjust `.env` if you have local PostgreSQL credentials. If `DATABASE_URL` is omitted, the development settings will automatically fall back to local `db.sqlite3`.

## 4. Compile Tailwind CSS

```bash
npm install
npm run build:css
# Or for live compilation during development:
npm run watch:css
```

## 5. Run Migrations & Start Server

```bash
python manage.py migrate
python manage.py runserver
```

The application is accessible at `http://127.0.0.1:8000/`.
The health-check endpoint is at `http://127.0.0.1:8000/health/`.

