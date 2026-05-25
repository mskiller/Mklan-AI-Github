FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace/backend/src:/workspace/worker/src

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        exiftool \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /workspace/backend/pyproject.toml
COPY backend/README.md /workspace/backend/README.md
COPY backend/alembic.ini /workspace/backend/alembic.ini
COPY backend/alembic /workspace/backend/alembic
COPY backend/src /workspace/backend/src
COPY worker/pyproject.toml /workspace/worker/pyproject.toml
COPY worker/README.md /workspace/worker/README.md
COPY worker/src /workspace/worker/src

RUN pip install --no-cache-dir -e /workspace/backend
RUN pip install --no-cache-dir -e /workspace/worker

WORKDIR /workspace/worker

CMD python -m media_indexer_worker.main

