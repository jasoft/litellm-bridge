#!/usr/bin/env bash
set -euo pipefail
: "${ELEVENLABS_API_KEY:?ELEVENLABS_API_KEY is required}"
exec litellm --host 0.0.0.0 --port 8046 --config /app/config.yaml
