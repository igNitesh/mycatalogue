# Docker Development Workflow

Using Docker Compose ensures parity between local development and production environments.

## Prerequisites
- Docker (v24+)
- Docker Compose (v2+ or docker-compose)

## 1. Quick Start

```bash
# 1. Prepare environment variables
cp .env.example .env

# 2. Build and start containers in the background
docker-compose up --build -d

# 3. View container logs
docker-compose logs -f
```

The web service will wait for the PostgreSQL database container health check before booting the Django dev server.

## 2. Common Docker Commands

### Running Django Management Commands
```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Open Django shell
docker-compose exec web python manage.py shell
```

### Running Tests in Docker
```bash
docker-compose exec web pytest
```

### Stopping Services
```bash
# Stop containers
docker-compose down

# Stop containers and wipe PostgreSQL volume
docker-compose down -v
```

