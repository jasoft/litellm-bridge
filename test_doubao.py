from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import doubao_api as stt
import doubao_stt


def test_worker_is_bounded_and_parses_json(monkeypatch):
    def run(command, **kwargs):
        assert command == [sys.executable, str(Path(stt.__file__).with_name("doubao_stt.py")), "a.wav"]
        assert kwargs["timeout"] == 15
        assert kwargs["capture_output"] is True
        if sys.platform == "darwin":
            assert "/opt/homebrew/lib" in kwargs["env"]["DYLD_LIBRARY_PATH"]
        return SimpleNamespace(returncode=0, stdout='{"text":" 南京 "}')

    monkeypatch.setattr(stt.subprocess, "run", run)
    assert stt.run_doubao_stt(Path("a.wav")) == "南京"


@pytest.mark.parametrize("code,body", [(1, ""), (0, "not-json"), (0, '{"text":null}'), (0, "[]")])
def test_worker_rejects_errors_and_invalid_responses(monkeypatch, code, body):
    monkeypatch.setattr(stt.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout=body))
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        stt.run_doubao_stt(Path("a.wav"))


def test_worker_uses_private_persistent_credentials(monkeypatch, tmp_path, capsys):
    credentials = tmp_path / "asr" / "credentials.json"

    class Config:
        def __init__(self, **kwargs):
            assert kwargs == {"credential_path": credentials, "connect_timeout": 5, "recv_timeout": 5}

        def ensure_credentials(self):
            credentials.write_text("{}")

    async def transcribe(path, *, config, realtime):
        assert path == Path("a.wav") and realtime is False
        return "识别成功"

    monkeypatch.setenv("DOUBAO_CREDENTIAL_PATH", str(credentials))
    monkeypatch.setattr(sys, "argv", ["doubao_stt", "a.wav"])
    monkeypatch.setattr(doubao_stt.os, "umask", lambda value: None)
    monkeypatch.setitem(sys.modules, "doubaoime_asr", SimpleNamespace(ASRConfig=Config, transcribe=transcribe))
    doubao_stt.main()
    assert json.loads(capsys.readouterr().out) == {"text": "识别成功"}
    assert credentials.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("result", [" 南京 ", "", RuntimeError("failed"), TimeoutError("slow")])
def test_internal_endpoint_reuses_engine_and_enforces_timeout(monkeypatch, result, caplog):
    from fastapi.testclient import TestClient
    caplog.set_level("INFO", logger="doubao_asr")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test-token")
    monkeypatch.setattr(stt, "_load_cached_engine", lambda: object())
    paths = []

    async def transcribe(path, *, config, realtime):
        paths.append(path)
        assert config is not None and path.read_bytes() == b"audio" and realtime is False
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(stt, "doubao_transcribe", transcribe)
    monkeypatch.setattr(stt, "run_doubao_stt", lambda *args: pytest.fail("Warm engine must not spawn a worker"))
    with TestClient(stt.app) as client:
        upload = {"file": ("a.wav", b"audio", "audio/wav")}
        assert client.post("/v1/audio/transcriptions", files=upload).status_code == 401
        response = client.post("/v1/audio/transcriptions", files=upload,
                               headers={"Authorization": "Bearer test-token",
                                        "X-PTT-Request-ID": "trace-123"})
        assert response.status_code == (200 if result == " 南京 " else 503)
        if response.status_code == 200:
            assert response.json() == {"text": "南京"}
            assert 'request_id":"trace-123"' in caplog.text
            assert 'event":"completed"' in caplog.text
            assert '"response_chars":2' in caplog.text
            assert "南京" not in caplog.text
        assert len(paths) == 1 and not paths[0].exists()
        assert client.post("/v1/audio/transcriptions", files={"file": ("a.wav", b"")},
                           headers={"Authorization": "Bearer test-token"}).status_code == 400


def test_missing_credentials_uses_bounded_worker_then_caches_engine(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test-token")
    calls = []
    engines = iter((None, object()))
    monkeypatch.setattr(stt, "_load_cached_engine", lambda: next(engines))

    def worker(path):
        calls.append(path)
        assert path.read_bytes() == b"audio"
        return "恢复后识别"

    monkeypatch.setattr(stt, "run_doubao_stt", worker)
    with TestClient(stt.app) as client:
        response = client.post("/v1/audio/transcriptions", files={"file": ("a.wav", b"audio")},
                               headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200 and response.json() == {"text": "恢复后识别"}
        assert len(calls) == 1 and not calls[0].exists()


def test_cached_engine_load_is_local_and_preserves_private_mode(monkeypatch, tmp_path):
    credentials = tmp_path / "asr" / "credentials.json"
    credentials.parent.mkdir()
    credentials.write_text('{"device_id":"device","token":"private"}')

    class Config:
        def __init__(self, **kwargs):
            assert kwargs == {"credential_path": credentials, "connect_timeout": 5, "recv_timeout": 5}
            self.initialized = False

        def ensure_credentials(self):
            self.initialized = True

    monkeypatch.setattr(stt, "CREDENTIALS", credentials)
    monkeypatch.setattr(stt, "ASRConfig", Config)
    engine = stt._load_cached_engine()
    assert engine.initialized
    assert credentials.stat().st_mode & 0o777 == 0o600
