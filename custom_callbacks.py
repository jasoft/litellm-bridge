import json
import sys
from collections.abc import Mapping
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger


class AudioUpload(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if call_type == "transcription":
            audio = data.get("file")
            if audio is not None and hasattr(audio, "read"):
                # OpenAI consumes the stream; immutable bytes survive provider fallbacks.
                data["file"] = (getattr(audio, "name", "audio.wav"), audio.read())
            file_value = data.get("file")
            audio_bytes = file_value[1] if isinstance(file_value, tuple) and len(file_value) > 1 else b""
            filename = file_value[0] if isinstance(file_value, tuple) and file_value else ""
            metadata = data.get("metadata") or {}
            headers = metadata.get("headers") if isinstance(metadata, Mapping) else {}
            request_id = headers.get("x-ptt-request-id") if isinstance(headers, Mapping) else None
            print("litellm_transcription_call " + json.dumps({
                "event": "received",
                "request_id": request_id,
                "litellm_call_id": data.get("litellm_call_id"),
                "requested_model": data.get("model"),
                "audio_bytes": len(audio_bytes) if isinstance(audio_bytes, bytes) else None,
                "file_extension": Path(str(filename)).suffix.lower() or None,
                "call_type": call_type,
            }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr, flush=True)
        return data


audio_upload = AudioUpload()
