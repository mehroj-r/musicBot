ARG PYTHON_VERSION=3.13.3

# ---- Stage 1: Builder ----
FROM python:${PYTHON_VERSION}-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies including Rust
RUN apk update && \
    apk add --no-cache \
        ca-certificates \
        gcc \
        musl-dev \
        lapack-dev \
        libffi-dev \
        openssl-dev \
        python3-dev \
        make \
        cmake \
        build-base \
        curl \
        rust \
        cargo && \
    rm -rf /var/cache/apk/*

# Install UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app_build

COPY pyproject.toml uv.lock ./

# Use UV to install dependencies
RUN uv sync --frozen

COPY . .

# ---- Stage 2: Final runtime image ----
FROM python:${PYTHON_VERSION}-alpine AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime dependencies
RUN apk update && \
    apk add --no-cache \
        ca-certificates \
        ffmpeg \
        libffi \
        openssl \
        libgcc && \
    rm -rf /var/cache/apk/* /tmp/*

WORKDIR /app

COPY --from=builder /app_build/.venv /app/.venv
COPY --from=builder /app_build/src ./src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PATH"

# Run the application
CMD ["python", "-m", "core.main"]