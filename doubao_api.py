from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

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


app = FastAPI()


@app.post("/v1/audio/transcriptions")
async def transcribe(file: Annotated[UploadFile, File()], authorization: Annotated[str, Header()] = ""):
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
            text = await asyncio.to_thread(run_doubao_stt, Path(audio.name))
        except (subprocess.SubprocessError, OSError, TypeError, ValueError, RuntimeError) as exc:
            print(f"Doubao STT failed: {type(exc).__name__}", file=sys.stderr)
            raise HTTPException(503, "Doubao transcription unavailable") from exc
    if not text:
        raise HTTPException(503, "Doubao returned no speech")
    return {"text": text}
