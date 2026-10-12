ARG PYTHON_VERSION=3.13

# ---- Stage 1: Builder ----
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first so code changes don't reinstall them
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Then install the bot itself as a regular package
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---- Stage 2: Final runtime image ----
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 musicbot

# ffmpeg converts audio (static build: a fraction of Debian's package size);
# deno lets yt-dlp solve YouTube's JavaScript challenges
COPY --from=mwader/static-ffmpeg:8.0 /ffmpeg /ffprobe /usr/local/bin/
COPY --from=denoland/deno:bin-2.9.6 /deno /usr/local/bin/deno

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
# Owned by the bot user so a fresh data volume starts out writable
RUN mkdir -p /app/data && chown musicbot:musicbot /app/data

USER musicbot
ENV PATH="/app/.venv/bin:$PATH"

CMD ["musicbot"]
