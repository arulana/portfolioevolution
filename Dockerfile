FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
COPY schemas/ schemas/
COPY data/ data/
COPY scripts/ scripts/

RUN pip install -e ".[dev]" 2>/dev/null || pip install -e .
RUN pip install fastapi uvicorn

EXPOSE 8000
EXPOSE 5433

CMD ["uvicorn", "portfolio_evolution.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
