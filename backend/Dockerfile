# Backend Dockerfile for FastAPI — uses uv for fast, reproducible installs

FROM python:3.11-slim

# Install uv (pinned for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first (Docker layer caching)
COPY pyproject.toml uv.lock .python-version ./

# Install dependencies into the system Python (no virtualenv inside container)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Install the project itself (editable)
RUN uv sync --frozen --no-dev

# Create models directory
RUN mkdir -p /app/models

# Expose port
EXPOSE 8000

# Run via uv so PATH includes the managed environment
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
