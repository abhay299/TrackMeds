# Same image runs on Cloud Run, Render, or your laptop — the host is a deploy
# detail, not a code concern. python:3.12-slim + uv keeps it ~150 MB.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, in their own layer: they change far less often than the
# code, so most rebuilds reuse this cached layer and take seconds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# Never run as root inside the container.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Cloud Run's default $PORT is 8080; the deploy script leaves it at that.
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
