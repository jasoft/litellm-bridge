FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir "litellm[proxy]==1.82.0"

WORKDIR /app
COPY config.yaml /app/config.yaml
COPY custom_callbacks.py /app/custom_callbacks.py
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8046
ENTRYPOINT ["/app/docker-entrypoint.sh"]
