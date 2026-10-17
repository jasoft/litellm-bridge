from __future__ import annotations

import asyncio
import fcntl
import json
import os
import secrets
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from doubaoime_asr import ASRConfig
from doubaoime_asr import transcribe as doubao_transcribe
from fastapi import FastAPI, File, Header, HTTPException, UploadFile


def run_doubao_stt(audio_file: Path) -> str:
    env = os.environ.copy()
    if sys.platform == "darwin":
        env["DYLD_LIBRARY_PATH"] = os.pathsep.join(
            filter(None, ("/opt/homebrew/lib", "/usr/local/lib", env.get("DYLD_LIBRARY_PATH")))
        )
    # Upstream registration uses blocking HTTP without a timeout; bound the whole worker.
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("doubao_stt.py")), str(audio_file)],
        capture_output=True, text=True, env=env, timeout=15, check=False,
    )
    if proc.returncode:
        raise RuntimeError("豆包语音识别失败")
    data = json.loads(proc.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        raise TypeError("豆包识别响应缺少文本")
    return data["text"].strip()


CREDENTIALS = Path(os.environ.get(
    "DOUBAO_CREDENTIAL_PATH", str(Path(__file__).resolve().parent / "data" / "doubao-asr-credentials.json")
)).expanduser()
_engine: ASRConfig | None = None


def _load_cached_engine() -> ASRConfig | None:
    try:
        cached = json.loads(CREDENTIALS.read_text())
        if not isinstance(cached, dict) or not cached.get("device_id") or not cached.get("token"):
            return None
        engine = ASRConfig(credential_path=CREDENTIALS, connect_timeout=5, recv_timeout=5)
        with CREDENTIALS.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            engine.ensure_credentials()
            CREDENTIALS.chmod(0o600)
        return engine
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"Doubao cached credentials unavailable: {type(exc).__name__}", file=sys.stderr)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    _engine = _load_cached_engine()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/v1/audio/transcriptions")
async def transcribe(file: Annotated[UploadFile, File()], authorization: Annotated[str, Header()] = ""):
    global _engine
    token = os.environ.get("LITELLM_MASTER_KEY", "")
    if not token or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Invalid API key")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Audio is empty")
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "audio.wav").suffix) as audio:
        audio.write(content)
        audio.flush()
        try:
            if _engine is None:
                text = await asyncio.to_thread(run_doubao_stt, Path(audio.name))
                _engine = _load_cached_engine()
            else:
                text = await asyncio.wait_for(
                    doubao_transcribe(Path(audio.name), config=_engine, realtime=False), timeout=15
                )
        except (TimeoutError, subprocess.SubprocessError, OSError, TypeError, ValueError, RuntimeError) as exc:
            print(f"Doubao STT failed: {type(exc).__name__}", file=sys.stderr)
            raise HTTPException(503, "Doubao transcription unavailable") from exc
    text = text.strip()
    if not text:
        raise HTTPException(503, "Doubao returned no speech")
    return {"text": text}
