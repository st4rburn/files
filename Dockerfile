FROM python:3.13-slim

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends media-types \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /shares
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/sh -m -d /app app
RUN chown app:app /app
RUN chown app:app /shares
USER app

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./

# Install deps on persistent cache mount
RUN --mount=type=cache,target=/app/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --no-install-project --no-dev

COPY src .
COPY templates templates
COPY static static

# Add uv venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "files:app", "--host", "0.0.0.0", "--port", "8000"]
