# Mklan Studio — Unified Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY migrations/ ./migrations/

# Default environment variables
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

# Wildcard module defaults
ENV WILDCARD_SOURCE_ROOT=/app/data/wildcards
ENV WILDCARD_WORKSHOP_DATA_DIR=/app/data/wildcards
ENV WILDCARD_WORKSHOP_DB=/app/data/wildcards/wildcard_workshop.db
ENV WILDCARD_EXPORT_ROOT=/app/data/exports

# Movie module defaults
ENV MOVIE_DATA_DIR=/app/data/movie
ENV MOVIE_DB=/app/data/movie/movie_tool.db

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
