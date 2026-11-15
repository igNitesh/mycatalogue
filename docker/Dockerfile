# syntax=docker/dockerfile:1
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Builder to compile wheels
FROM base as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ /requirements/
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r /requirements/development.txt -r /requirements/production.txt

# Stage 3: Development / Final runtime
FROM base as development

# Create non-root user
RUN groupadd -r django && useradd -r -g django -d /home/django -m django

# Install pre-built wheels
COPY --from=builder /wheels /wheels
COPY requirements/ /requirements/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy project files
COPY . /app

# Ensure entrypoint is executable and directory is owned by django
RUN chmod +x /app/docker/entrypoint.sh && \
    chown -R django:django /app

USER django

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Stage 4: Production
FROM base as production

RUN groupadd -r django && useradd -r -g django -d /home/django -m django

COPY --from=builder /wheels /wheels
COPY requirements/ /requirements/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

COPY . /app

RUN chmod +x /app/docker/entrypoint.sh && \
    chown -R django:django /app

USER django

ENV DJANGO_SETTINGS_MODULE=config.settings.production

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
