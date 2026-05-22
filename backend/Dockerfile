# Glass Sidebar backend — the API server and the Arq worker share this image.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Dependency layer — cached unless pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code.
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Default command runs the API. The worker service overrides this in
# docker-compose.yml.
CMD ["uv", "run", "uvicorn", "glass.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
