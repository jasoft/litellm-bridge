import litellm
from typing import Any
from litellm.integrations.custom_logger import CustomLogger
from litellm.types.utils import TranscriptionResponse

# FORCE GLOBAL FLAGS
litellm.drop_params = True

class TextCleaner(CustomLogger):
    """
    This callback ensures ElevenLabs Scribe V2 receives the correct parameters
    to natively handle filler word removal and audio event filtering.
    """
    async def async_pre_call_hook(self, user_api_key_dict: Any, model: str, messages: Any, data: dict, temp_response_obj: Any):
        """
        Pre-call hook to inject ElevenLabs specific parameters for native cleaning.
        """
        if data.get("call_type") == "audio_transcription":
            optional_params = data.get("optional_params", {})
            
            # Enable native ElevenLabs cleaning features
            optional_params["no_verbatim"] = True      # Removes filler words (uh, um, etc.) natively
            optional_params["tag_audio_events"] = False # Disables (clap), [laugh] etc. natively
            
            # Drop problematic OpenAI-default parameters that cause 400 errors
            keys_to_remove = ["user", "encoding_format", "response_format"]
            for key in keys_to_remove:
                if key in optional_params:
                    del optional_params[key]
            
            data["optional_params"] = optional_params
            
        return data

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict: Any, response: Any):
        """
        Post-call hook (now just a pass-through, letting STT do the work).
        """
        return response

# Instantiate the handler for LiteLLM
cleaner_instance = TextCleaner()
