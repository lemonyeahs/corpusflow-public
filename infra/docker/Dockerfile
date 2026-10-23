FROM python:3.12.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY scripts scripts
RUN useradd --uid 10001 --create-home corpusflow
USER corpusflow
