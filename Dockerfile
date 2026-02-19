# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first (layer-cache friendly)
COPY pyproject.toml uv.lock* ./

# Install production dependencies into an isolated venv
RUN uv sync --frozen --no-dev

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for least-privilege execution
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Bring the venv from the builder
COPY --from=builder /app/.venv /app/.venv

# Bring application source
COPY main.py ./

# Make venv binaries available on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

ENTRYPOINT ["python", "main.py"]