import os
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

CONFIG_PATH = os.environ.get("LITELLM_CONFIG_PATH", str(Path(__file__).with_name("config.yaml")))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = os.environ.get("PORT", "8046")


def configure_keys(config: dict) -> dict:
    keys = list(dict.fromkeys(
        key.strip() for key in os.environ.get(
            "ELEVENLABS_API_KEYS", os.environ.get("ELEVENLABS_API_KEY", "")
        ).split(",") if key.strip()
    ))
    if not keys:
        raise ValueError("ELEVENLABS_API_KEY or ELEVENLABS_API_KEYS is required")
    os.environ.setdefault("ELEVENLABS_API_KEY", keys[0])
    config = deepcopy(config)
    primary = next(m for m in config["model_list"] if m["model_name"] == "elevenlabs-transcription")
    backups = []
    for index, key in enumerate(keys):
        env_name = f"ELEVENLABS_STT_KEY_{index}"
        os.environ[env_name] = key
        deployment = primary if index == 0 else deepcopy(primary)
        deployment["litellm_params"]["api_key"] = f"os.environ/{env_name}"
        if index:
            deployment["model_name"] = f"elevenlabs-transcription-backup-{index}"
            config["model_list"].append(deployment)
            backups.append(deployment["model_name"])
    if backups:
        router = config.setdefault("router_settings", {})
        router.setdefault("fallbacks", []).append({"elevenlabs-transcription": backups})
        router["num_retries"] = 0
        router["max_fallbacks"] = len(backups)
    return config


def main() -> None:
    with open(CONFIG_PATH) as source:
        config = configure_keys(yaml.safe_load(source))
    # LiteLLM resolves custom callbacks relative to the configuration file.
    with NamedTemporaryFile(
        mode="w", prefix=".runtime-", suffix=".yaml", dir=Path(CONFIG_PATH).parent, delete=False
    ) as runtime:
        yaml.safe_dump(config, runtime)

    os.execvp(
        "litellm",
        [
            "litellm",
            "--host",
            HOST,
            "--port",
            PORT,
            "--config",
            runtime.name,
        ],
    )

if __name__ == "__main__":
    main()
