FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /workspace/backend/pyproject.toml
COPY backend/README.md /workspace/backend/README.md
COPY backend/alembic.ini /workspace/backend/alembic.ini
COPY backend/alembic /workspace/backend/alembic
COPY backend/src /workspace/backend/src

RUN pip install --no-cache-dir -e /workspace/backend

WORKDIR /workspace/backend

CMD alembic upgrade head && uvicorn media_indexer_backend.main:app --host 0.0.0.0 --port 8000
