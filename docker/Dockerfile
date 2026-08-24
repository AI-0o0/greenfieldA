FROM python:3.12-slim

# Install uv from the official binary image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    GREENFIELD_PLATFORM_HOST=0.0.0.0 \
    GREENFIELD_PLATFORM_PORT=8000 \
    GREENFIELD_DB_PATH=/app/db/farm.db \
    GREENFIELD_CHECKPOINT_DB=/app/db/checkpoints.sqlite

# 1. Install dependencies first for optimal layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2. Copy the application source code
COPY . .

# 3. Final sync including application
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Start the unified web platform & MCP server
CMD ["uvicorn", "website.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]