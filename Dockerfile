FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

COPY --from=uv /uv /uvx /bin/
RUN uv tool install --python /usr/local/bin/python "litellm[proxy]==1.82.3"

WORKDIR /app
COPY config.yaml /app/config.yaml
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8046
ENTRYPOINT ["/app/docker-entrypoint.sh"]
