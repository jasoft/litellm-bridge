# LiteLLM ElevenLabs Bridge

Exposes OpenAI-compatible endpoints for:
- `elevenlabs-tts`
- `elevenlabs-transcription`

## Build
```bash
docker build -t litellm-elevenlabs-bridge:latest .
```

## Run
```bash
docker run -d \
  --name litellm-elevenlabs-bridge \
  --restart unless-stopped \
  -p 8046:8046 \
  -e ELEVENLABS_API_KEY=your_key_here \
  litellm-elevenlabs-bridge:latest
```

## Test
```bash
curl -H 'Authorization: Bearer local-noauth' http://127.0.0.1:8046/v1/models
```
