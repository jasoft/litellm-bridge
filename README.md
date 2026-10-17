# LiteLLM 语音网关

通过同一套 OpenAI 兼容接口提供豆包 ASR、ElevenLabs STT 和 TTS。
远程容器为 `litellm-elevenlabs-bridge`，端口 `8046`。

| 模型名 | 行为 |
| --- | --- |
| `doubao-transcription` | 豆包识别；失败、超时或空结果时按顺序尝试 ElevenLabs 的所有 Key |
| `elevenlabs-transcription` | 原 ElevenLabs Scribe v2，保留为独立备用入口；仍支持多 Key 切换 |
| `elevenlabs-tts` | 原 ElevenLabs TTS |

接口包括 `POST /v1/audio/transcriptions`、`POST /v1/audio/speech` 和 `GET /v1/models`。
原模型名与认证保持兼容；其他 App 选择 `doubao-transcription` 即可使用新的识别服务。

## 调用

Base URL：`http://docker.home:8046/v1`。认证使用现有 `LITELLM_MASTER_KEY`，不要把真实密钥提交到代码。

```python
import os
from openai import OpenAI

client = OpenAI(base_url="http://docker.home:8046/v1", api_key=os.environ["LITELLM_MASTER_KEY"])
with open("sample.wav", "rb") as audio:
    result = client.audio.transcriptions.create(model="doubao-transcription", file=audio)
print(result.text)
```

```bash
curl http://docker.home:8046/v1/audio/transcriptions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -F file=@sample.wav -F model=doubao-transcription
```

需要直接使用原 STT 时将模型名改为 `elevenlabs-transcription`。
豆包当前返回 `{"text": "识别结果"}`，不提供逐字时间戳或字幕格式。

## 部署

`.env` 必填 `LITELLM_MASTER_KEY` 和 `ELEVENLABS_API_KEY`（或逗号分隔的 `ELEVENLABS_API_KEYS`）。
ElevenLabs Key 列表去重后按顺序尝试，TTS 使用单 Key，未设置时使用列表首项。
可选 `ELEVENLABS_API_BASE`、`HOST`、`PORT`、`LITELLM_CONFIG_PATH`。

```bash
cp .env.example .env
# 填入密钥后执行
mkdir -p data
docker compose up -d --build
```

豆包使用 [doubao-asr-free](https://github.com/RayMorTwinkle/doubao-asr-free)，固定到
`7a99097e8e4ed4a58c57f975346689d724fde6a3`。Docker 包含 `libopus0`。
凭据默认保存在挂载的 `data/doubao-asr-credentials.json`，权限 `0600`，首次自动注册；
也可以安全复制已有凭据。可用 `DOUBAO_CREDENTIAL_PATH` 指定路径。
不要把 `data/` 加入镜像或提交到 Git。

容器入口启动豆包内部适配服务（仅监听 `127.0.0.1:8047`），然后启动 LiteLLM。
外部请求统一经过 LiteLLM 的认证、模型路由和 fallback；内部接口也要求相同密钥。
豆包库在内部 ASR 服务启动时加载并常驻内存（实测约 66 MB RSS、51 MB PSS），识别调用共享已加载的库和缓存凭据；识别单次上限 15 秒。凭据缓存缺失或无效时保留有界子进程恢复路径。错误不会泄露凭据。
现有 ElevenLabs TTS 参数保持原样，能否使用仍取决于账户额度和音色权限。

## 本地运行与验证

macOS 需先安装 `brew install opus`。加载 `.env` 后：

```bash
uv sync --group dev
HOST=127.0.0.1 uv run python main.py
uv run pytest test_keys.py test_doubao.py -q
uv run ruff check main.py doubao_api.py doubao_stt.py test_doubao.py
```

测试覆盖多 Key、豆包失败后的原音频重传、内部鉴权、超时、常驻识别和凭据恢复。
