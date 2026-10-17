from litellm.integrations.custom_logger import CustomLogger


class AudioUpload(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if call_type == "transcription":
            audio = data.get("file")
            if audio is not None and hasattr(audio, "read"):
                # OpenAI consumes the stream; immutable bytes survive provider fallbacks.
                data["file"] = (getattr(audio, "name", "audio.wav"), audio.read())
        return data


audio_upload = AudioUpload()
