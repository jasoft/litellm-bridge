from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import miniaudio
from doubaoime_asr import ASRConfig
from doubaoime_asr import transcribe as doubao_transcribe
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile


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
    print(f"doubao_asr_engine_ready resident={_engine is not None}", file=sys.stderr, flush=True)
    yield


app = FastAPI(lifespan=lifespan)


def _audio_duration_ms(path: Path) -> int | None:
    try:
        return round(miniaudio.get_file_info(str(path)).duration * 1000)
    except (miniaudio.DecodeError, OSError):
        return None


def _call_log(level: int, **details: object) -> None:
    print(logging.getLevelName(level) + " doubao_asr_call " +
          json.dumps(details, ensure_ascii=False, separators=(",", ":")),
          file=sys.stderr, flush=True)


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: Annotated[UploadFile, File()],
    request: Request,
    authorization: Annotated[str, Header()] = "",
):
    global _engine
    started = time.perf_counter()
    supplied_id = request.headers.get("x-ptt-request-id", "")
    proxy_call_id = request.headers.get("x-litellm-call-id", "")
    request_id = next((value for value in (supplied_id, proxy_call_id)
                       if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)), uuid.uuid4().hex)
    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    engine_mode = "resident" if _engine is not None else "worker-bootstrap"
    _call_log(logging.INFO, event="start", request_id=request_id, route=request.url.path,
              litellm_call_id=proxy_call_id or None,
              requested_model="doubao-transcription", engine_mode=engine_mode,
              content_type=file.content_type, file_extension=suffix)

    token = os.environ.get("LITELLM_MASTER_KEY", "")
    if not token or not secrets.compare_digest(authorization, f"Bearer {token}"):
        _call_log(logging.WARNING, event="rejected", request_id=request_id, http_status=401,
                  error_type="AuthenticationError", total_ms=round((time.perf_counter() - started) * 1000, 1))
        raise HTTPException(401, "Invalid API key")
    upload_started = time.perf_counter()
    content = await file.read()
    if not content:
        _call_log(logging.WARNING, event="rejected", request_id=request_id, http_status=400,
                  error_type="EmptyAudio", total_ms=round((time.perf_counter() - started) * 1000, 1))
        raise HTTPException(400, "Audio is empty")
    upload_ms = round((time.perf_counter() - upload_started) * 1000, 1)
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "audio.wav").suffix) as audio:
        audio.write(content)
        audio.flush()
        audio_duration_ms = _audio_duration_ms(Path(audio.name))
        # Doubao drops earlier rolling windows around 23s; let LiteLLM replay the whole upload to Scribe.
        if audio_duration_ms is None or audio_duration_ms > 20_000:
            _call_log(logging.INFO, event="delegated", request_id=request_id,
                      requested_model="doubao-transcription", audio_bytes=len(content),
                      audio_duration_ms=audio_duration_ms,
                      reason="duration_unknown" if audio_duration_ms is None else "audio_too_long",
                      http_status=503, total_ms=round((time.perf_counter() - started) * 1000, 1))
            raise HTTPException(503, "Audio requires full-length transcription fallback")
        asr_started = time.perf_counter()
        try:
            if _engine is None:
                text = await asyncio.to_thread(run_doubao_stt, Path(audio.name))
                _engine = _load_cached_engine()
                engine_mode = "worker-bootstrap"
            else:
                text = await asyncio.wait_for(
                    doubao_transcribe(Path(audio.name), config=_engine, realtime=False), timeout=15
                )
        except (TimeoutError, subprocess.SubprocessError, OSError, TypeError, ValueError, RuntimeError) as exc:
            _call_log(logging.ERROR, event="failed", request_id=request_id,
                      requested_model="doubao-transcription", engine_mode=engine_mode,
                      audio_bytes=len(content), audio_duration_ms=audio_duration_ms,
                      upload_ms=upload_ms,
                      asr_ms=round((time.perf_counter() - asr_started) * 1000, 1),
                      total_ms=round((time.perf_counter() - started) * 1000, 1),
                      error_type=type(exc).__name__, http_status=503)
            raise HTTPException(503, "Doubao transcription unavailable") from exc
    text = text.strip()
    if not text:
        _call_log(logging.WARNING, event="empty_result", request_id=request_id,
                  requested_model="doubao-transcription", engine_mode=engine_mode,
                  audio_bytes=len(content), audio_duration_ms=audio_duration_ms,
                  upload_ms=upload_ms,
                  asr_ms=round((time.perf_counter() - asr_started) * 1000, 1),
                  total_ms=round((time.perf_counter() - started) * 1000, 1), http_status=503)
        raise HTTPException(503, "Doubao returned no speech")
    _call_log(logging.INFO, event="completed", request_id=request_id,
              requested_model="doubao-transcription", engine_mode=engine_mode,
              audio_bytes=len(content), audio_duration_ms=audio_duration_ms,
              upload_ms=upload_ms,
              asr_ms=round((time.perf_counter() - asr_started) * 1000, 1),
              total_ms=round((time.perf_counter() - started) * 1000, 1),
              response_chars=len(text), http_status=200)
    return {"text": text}
