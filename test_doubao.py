from __future__ import annotations

import json
import subprocess
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


@pytest.mark.parametrize("result", [" 南京 ", "", RuntimeError("failed"), subprocess.TimeoutExpired("asr", 15)])
def test_internal_endpoint_auth_and_provider_errors(monkeypatch, result):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test-token")
    paths = []

    def run(path):
        paths.append(path)
        assert path.read_bytes() == b"audio"
        if isinstance(result, Exception):
            raise result
        return result.strip()

    monkeypatch.setattr(stt, "run_doubao_stt", run)
    client = TestClient(stt.app)
    upload = {"file": ("a.wav", b"audio", "audio/wav")}
    assert client.post("/v1/audio/transcriptions", files=upload).status_code == 401
    response = client.post("/v1/audio/transcriptions", files=upload,
                           headers={"Authorization": "Bearer test-token"})
    assert response.status_code == (200 if result == " 南京 " else 503)
    if response.status_code == 200:
        assert response.json() == {"text": "南京"}
    assert len(paths) == 1 and not paths[0].exists()
    assert client.post("/v1/audio/transcriptions", files={"file": ("a.wav", b"")},
                       headers={"Authorization": "Bearer test-token"}).status_code == 400
