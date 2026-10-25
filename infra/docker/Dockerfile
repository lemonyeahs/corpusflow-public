FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
COPY --from=ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 /uv /usr/local/bin/uv
# Explicit OCR package versions; upgrade deliberately with image/regression evidence.
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    tesseract-ocr=5.5.0-1+b1 tesseract-ocr-eng=1:4.1.0-2 \
    poppler-utils=25.03.0-5+deb13u4 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_HTTP_TIMEOUT=120 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY alembic.ini ./
COPY scripts scripts
RUN useradd --uid 10001 --create-home corpusflow
USER corpusflow
