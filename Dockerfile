FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       ca-certificates \
       build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY frontend/control-center/dist ./frontend/control-center/dist
COPY brain.py ./brain.py
COPY gamma_crawler.py ./gamma_crawler.py
COPY polymarket_orderbook_sample.json ./polymarket_orderbook_sample.json

ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        uv pip install --system --no-cache ".[dev]"; \
    else \
        uv pip install --system --no-cache .; \
    fi

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
