# LiteLLM ElevenLabs Bridge

一个把 ElevenLabs 语音接口暴露成 OpenAI 兼容 API 的轻量桥接服务。

当前支持：
- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`
- `GET /v1/models`

桥接基于 LiteLLM 内置的 ElevenLabs provider：
- OpenAI 风格的 `/v1/audio/transcriptions`
- 上游实际调用 ElevenLabs 官方 `/v1/speech-to-text`

默认暴露两个模型名：
- `elevenlabs-transcription`
- `elevenlabs-tts`

## 适用场景

- 你已经有一套 OpenAI SDK / OpenAI API 兼容调用链
- 你想把 STT/TTS 上游切到 ElevenLabs
- 你希望本地、Docker、远端服务器都用同一套配置
- 你希望 agent 可以直接读 README 就知道怎么启动、验证和排障

## 项目结构

运行时真正需要的文件很少：

```text
config.yaml
docker-entrypoint.sh
Dockerfile
main.py
README.md
```

说明：
- [config.yaml](/Users/weiwang/Projects/litellm-bridge/config.yaml) 定义模型映射和认证配置
- [docker-entrypoint.sh](/Users/weiwang/Projects/litellm-bridge/docker-entrypoint.sh) 是容器入口
- [main.py](/Users/weiwang/Projects/litellm-bridge/main.py) 提供本地 `python main.py` 启动方式

## 环境变量

必填：

```bash
ELEVENLABS_API_KEY=...
```

可选：

```bash
ELEVENLABS_API_BASE=https://api.elevenlabs.io
HOST=0.0.0.0
PORT=8046
LITELLM_CONFIG_PATH=/app/config.yaml
```

示例 `.env`：

```bash
cp .env.example .env
```

## 本地运行

推荐直接用 `uv`：

```bash
set -a
source .env
set +a

uv run --with 'litellm[proxy]==1.82.3' \
  litellm --host 127.0.0.1 --port 8046 --config config.yaml
```

如果你就是想走项目入口：

```bash
set -a
source .env
set +a

uv run python main.py
```

## Docker 运行

构建：

```bash
docker build -t litellm-elevenlabs-bridge:latest .
```

运行：

```bash
docker run -d \
  --name litellm-elevenlabs-bridge \
  --restart unless-stopped \
  -p 8046:8046 \
  --env-file .env \
  litellm-elevenlabs-bridge:latest
```

## OpenAI 兼容调用

认证头固定使用：

```text
Authorization: Bearer local-noauth
```

这是因为 [config.yaml](/Users/weiwang/Projects/litellm-bridge/config.yaml#L19) 里把 LiteLLM `master_key` 固定成了 `local-noauth`。

### 1. 查看模型

```bash
curl -H 'Authorization: Bearer local-noauth' \
  http://127.0.0.1:8046/v1/models
```

### 2. 语音转写

```bash
curl http://127.0.0.1:8046/v1/audio/transcriptions \
  -H 'Authorization: Bearer local-noauth' \
  -F file='@sample.wav' \
  -F model='elevenlabs-transcription'
```

返回示例：

```json
{
  "text": "Hello from Little Bridge.",
  "task": "transcribe",
  "language": "eng",
  "words": [
    { "word": "Hello", "start": 0.119, "end": 0.459 }
  ]
}
```

### 3. 文字转语音

```bash
curl http://127.0.0.1:8046/v1/audio/speech \
  -H 'Authorization: Bearer local-noauth' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "elevenlabs-tts",
    "input": "Hello from LiteLLM bridge.",
    "voice": "alloy",
    "response_format": "mp3"
  }' \
  --output speech.mp3
```

注意：
- TTS 是否成功还取决于 ElevenLabs 账户权限和 voice 可用性
- 某些免费账户会在默认 library voice 上收到 `paid_plan_required`

## OpenAI Python SDK 示例

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8046/v1",
    api_key="local-noauth",
)

with open("sample.wav", "rb") as audio_file:
    result = client.audio.transcriptions.create(
        model="elevenlabs-transcription",
        file=audio_file,
    )

print(result.text)
```

## 当前模型映射

见 [config.yaml](/Users/weiwang/Projects/litellm-bridge/config.yaml#L1)：

- `elevenlabs-transcription` -> `elevenlabs/scribe_v2`
- `elevenlabs-tts` -> `elevenlabs/eleven_multilingual_v2`

STT 额外启用了：
- `no_verbatim: true`
- `tag_audio_events: false`

这意味着：
- 尽量去掉 filler words
- 尽量不输出 `(laughter)`、`(clap)` 之类的事件标签

## Agent Notes

给 agent 的最小操作集：

1. 启动服务

```bash
set -a
source .env
set +a
uv run --with 'litellm[proxy]==1.82.3' litellm --host 127.0.0.1 --port 8046 --config config.yaml
```

2. 健康检查

```bash
curl -H 'Authorization: Bearer local-noauth' http://127.0.0.1:8046/v1/models
```

3. 转写检查

```bash
curl http://127.0.0.1:8046/v1/audio/transcriptions \
  -H 'Authorization: Bearer local-noauth' \
  -F file='@sample.wav' \
  -F model='elevenlabs-transcription'
```

4. Docker 部署

```bash
docker build -t litellm-elevenlabs-bridge:latest .
docker rm -f litellm-elevenlabs-bridge || true
docker run -d \
  --name litellm-elevenlabs-bridge \
  --restart unless-stopped \
  -p 8046:8046 \
  --env-file .env \
  litellm-elevenlabs-bridge:latest
```

## 常见问题

### 1. `ELEVENLABS_API_KEY is required`

说明环境变量没有注入。

检查：

```bash
set -a
source .env
set +a
env | rg ELEVENLABS
```

### 2. `/v1/models` 可用，但转写失败

通常是以下几类问题：
- 音频文件本身无有效语音
- ElevenLabs key 无效
- 上游 API Base 配错
- 请求没带 `Authorization: Bearer local-noauth`

### 3. TTS 报 `paid_plan_required`

这不是桥接层问题，是 ElevenLabs 账户权限或 voice 权限问题。

### 4. Docker 启动后请求被 reset

先看日志：

```bash
docker logs -f litellm-elevenlabs-bridge
```

再检查模型：

```bash
curl -H 'Authorization: Bearer local-noauth' http://127.0.0.1:8046/v1/models
```

## 开发

安装开发依赖：

```bash
uv sync --group dev
```

静态检查：

```bash
uv run ruff check .
uv run pyright
```
