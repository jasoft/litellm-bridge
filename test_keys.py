import asyncio
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import litellm
from litellm.exceptions import AuthenticationError
from litellm.router import Router
from litellm.types.utils import TranscriptionResponse

import main
from main import configure_keys

CONFIG = {"model_list": [{
    "model_name": "elevenlabs-transcription",
    "litellm_params": {"model": "elevenlabs/scribe_v2", "api_key": "os.environ/ELEVENLABS_API_KEY"},
}]}


class KeyTests(unittest.TestCase):
    def test_startup_keeps_config_next_to_callbacks(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "config.yaml"
            source.write_text(json.dumps(CONFIG))
            with patch.dict(os.environ, {"ELEVENLABS_API_KEYS": "first,second"}), \
                    patch.object(main, "CONFIG_PATH", str(source)), \
                    patch.object(os, "execvp") as launch:
                main.main()
                generated = Path(launch.call_args.args[1][-1])
                self.assertEqual(generated.parent, source.parent)
                self.assertIn("elevenlabs-transcription-backup-1", generated.read_text())

    def test_http_failover_replays_uploaded_audio(self):
        calls = []
        audio = b"RIFF-test-audio-payload"

        class Upstream(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                key = self.headers["xi-api-key"]
                calls.append((key, body))
                status = {"first": 401, "second": 429, "third": 200}[key]
                payload = {"text": "测试转写"} if status == 200 else {"detail": {"status": "quota_exceeded"}}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            async def run():
                with patch.dict(os.environ, {"ELEVENLABS_API_KEYS": "first,second,third", "NO_PROXY": "127.0.0.1"}):
                    config = configure_keys(CONFIG)
                    for model in config["model_list"]:
                        model["litellm_params"]["api_base"] = f"http://127.0.0.1:{server.server_port}"
                    router = Router(model_list=config["model_list"], **config["router_settings"])
                    result = await router.atranscription(
                        model="elevenlabs-transcription", file=("test.wav", io.BytesIO(audio), "audio/wav")
                    )
                    assert isinstance(result, TranscriptionResponse)
                    self.assertEqual(result.text, "测试转写")
            asyncio.run(run())
            self.assertEqual([key for key, _ in calls], ["first", "second", "third"])
            self.assertTrue(all(audio in body for _, body in calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_legacy_and_validation(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "legacy"}, clear=True):
            config = configure_keys(CONFIG)
            self.assertEqual(len(config["model_list"]), 1)
            self.assertEqual(os.environ["ELEVENLABS_STT_KEY_0"], "legacy")
            self.assertNotIn("router_settings", config)
        with patch.dict(os.environ, {"ELEVENLABS_API_KEYS": " , "}, clear=True), self.assertRaises(ValueError):
            configure_keys(CONFIG)

    def test_list_deduplicates_and_preserves_config(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEYS": "first, ,second,first,third"}, clear=True):
            config = configure_keys(CONFIG)
            self.assertEqual(len(config["model_list"]), 3)
            self.assertEqual(config["router_settings"]["max_fallbacks"], 2)
            self.assertEqual(os.environ["ELEVENLABS_STT_KEY_2"], "third")
            self.assertNotIn("first", str(config))
        self.assertEqual(len(CONFIG["model_list"]), 1)

    def test_router_fails_over_and_reports_exhaustion(self):
        async def run(all_exhausted):
            calls = []

            async def transcribe(**kwargs):
                calls.append(kwargs["api_key"])
                if kwargs["api_key"] != "third" or all_exhausted:
                    raise AuthenticationError(
                        message='{"detail":{"status":"quota_exceeded"}}',
                        llm_provider="elevenlabs", model="scribe_v2",
                    )
                return litellm.TranscriptionResponse(text="测试转写")

            with patch.dict(os.environ, {"ELEVENLABS_API_KEYS": "first,second,third"}):
                config = configure_keys(CONFIG)
                router = Router(model_list=config["model_list"], **config["router_settings"])
                with patch.object(litellm, "atranscription", side_effect=transcribe):
                    if all_exhausted:
                        with self.assertRaises(AuthenticationError):
                            await router.atranscription(model="elevenlabs-transcription", file=b"audio")
                    else:
                        result = await router.atranscription(model="elevenlabs-transcription", file=b"audio")
                        assert isinstance(result, TranscriptionResponse)
                        self.assertEqual(result.text, "测试转写")
                self.assertEqual(calls, ["first", "second", "third"])

        asyncio.run(run(False))
        asyncio.run(run(True))


if __name__ == "__main__":
    unittest.main()
