FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

COPY --from=uv /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends git libopus0 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /tmp/deps/pyproject.toml
RUN cd /tmp/deps && uv export --no-dev --no-emit-project --no-hashes -o requirements.txt && uv pip install --system -r requirements.txt

WORKDIR /app
COPY config.yaml /app/config.yaml
COPY main.py doubao_api.py doubao_stt.py custom_callbacks.py /app/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8046
ENTRYPOINT ["/app/docker-entrypoint.sh"]
